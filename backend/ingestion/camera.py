from __future__ import annotations
import base64
import json
from pathlib import Path
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Sequence
import os

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv(*args, **kwargs):
        return False


import cv2
import imageio_ffmpeg
import paho.mqtt.client as mqtt

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.database import save_analysis
from ingestion.buffers.mqtt_event_buffer import BufferedMqttEvent, MqttEventRingBuffer
from ingestion.buffers.rtsp_hot_buffer import BufferedFrame, FrameRingBuffer
from ingestion.record_ffmpeg import start_recording_ffmpeg, stop_recording

AnalysisMode = Literal["matched_frame", "snapshot", "periodic_frame"]

DEFAULT_ANALYSIS_DESCRIPTORS = [
    "white_clothes",
    "man",
    "woman",
    "gray_clothes",
    "green_clothes",
]

DEFAULT_ANALYSIS_TARGET_SAMPLES = 10
DEFAULT_MIN_ANALYSIS_INTERVAL_SECONDS = 1.0


def calculate_adaptive_analysis_interval_seconds(
    total_duration_seconds: float,
    *,
    target_samples: int = DEFAULT_ANALYSIS_TARGET_SAMPLES,
    min_interval_seconds: float = DEFAULT_MIN_ANALYSIS_INTERVAL_SECONDS,
) -> float:
    """Spread analysis over a duration while never sampling faster than the minimum interval."""
    if target_samples <= 0:
        raise ValueError("target_samples must be greater than 0")
    if min_interval_seconds <= 0:
        raise ValueError("min_interval_seconds must be greater than 0")

    total_duration = float(total_duration_seconds)
    if total_duration <= 0:
        return float(min_interval_seconds)

    return max(total_duration / float(target_samples), float(min_interval_seconds))


class Camera:
    def __init__(
        self,
        camera_id: str,
        rtsp_url: str,
        ffmpeg: str,
        broker_host: str,
        broker_port: int,
        analysis_client=None,
        segment_seconds: int = 10,
        hot_buffer_seconds: int = 30,
        hot_buffer_fps: int = 5,
        hot_buffer_max_bytes: int = 50 * 1024 * 1024, #TODO increase max bytes if needed
        mqtt_buffer_max_events: int = 300,
        mqtt_buffer_max_bytes: int = 5 * 1024 * 1024,
        hot_buffer_jpeg_quality: int = 70,
        hot_buffer_max_width: int = 960,
        analysis_mode: AnalysisMode = "matched_frame",
        analysis_interval_seconds: float = 5.0,
        analysis_descriptors: Optional[Sequence[str]] = None,
        analysis_target_samples: int = DEFAULT_ANALYSIS_TARGET_SAMPLES,
        min_analysis_interval_seconds: float = DEFAULT_MIN_ANALYSIS_INTERVAL_SECONDS,
    ) -> None:
        if analysis_mode not in {"matched_frame", "snapshot", "periodic_frame"}:
            raise ValueError(f"Unsupported analysis_mode={analysis_mode!r}")
        if analysis_target_samples <= 0:
            raise ValueError("analysis_target_samples must be greater than 0")
        if min_analysis_interval_seconds <= 0:
            raise ValueError("min_analysis_interval_seconds must be greater than 0")

        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.recording_process = None
        self.mqtt_client = mqtt.Client()

        self.hot_buffer_seconds = hot_buffer_seconds
        self.hot_buffer_fps = hot_buffer_fps
        self.hot_buffer_max_bytes = hot_buffer_max_bytes
        self.mqtt_buffer_max_events = mqtt_buffer_max_events
        self.mqtt_buffer_max_bytes = mqtt_buffer_max_bytes
        self.hot_buffer_jpeg_quality = hot_buffer_jpeg_quality
        self.hot_buffer_max_width = hot_buffer_max_width
        self.analysis_mode = analysis_mode
        self.analysis_target_samples = int(analysis_target_samples)
        self.min_analysis_interval_seconds = float(min_analysis_interval_seconds)
        self.analysis_interval_seconds = max(
            float(analysis_interval_seconds),
            self.min_analysis_interval_seconds,
        )
        self.analysis_descriptors = list(analysis_descriptors or DEFAULT_ANALYSIS_DESCRIPTORS)

        self.frame_buffer: FrameRingBuffer | None = None
        self.mqtt_buffer = MqttEventRingBuffer(
            max_events=self.mqtt_buffer_max_events,
            max_bytes=self.mqtt_buffer_max_bytes,
        )
        self._buffer_stop_event = threading.Event()
        self._buffer_thread: threading.Thread | None = None
        self._analysis_stop_event = threading.Event()
        self._analysis_thread: threading.Thread | None = None
        self._last_periodic_analysis_timestamp: datetime | None = None
        self.analysis_client = analysis_client

        self.init_recording(ffmpeg, segment_seconds)
        self.init_buffer()
        self.init_mqtt(broker_host, broker_port)
        self.init_periodic_analysis()

    def init_recording(self, ffmpeg: str, segment_seconds: int) -> None:
        self.recording_process = start_recording_ffmpeg(
            ffmpeg, self.rtsp_url, self.camera_id, segment_seconds
        )

    def init_mqtt(self, broker_host: str, broker_port: int) -> None:
        self.mqtt_client.connect(broker_host, broker_port, 60)
        self.mqtt_client.on_message = self.on_message
        self.mqtt_client.subscribe(f"camera/{self.camera_id}")
        self.mqtt_client.loop_start()

    def init_periodic_analysis(self) -> None:
        if self.analysis_mode != "periodic_frame":
            return

        self._analysis_stop_event.clear()
        self._analysis_thread = threading.Thread(
            target=self._periodic_analysis_loop,
            name=f"camera-{self.camera_id}-periodic-analysis",
            daemon=True,
        )
        self._analysis_thread.start()

    def on_message(self, client, userdata, msg) -> None:
        try:
            payload = msg.payload.decode("utf-8", errors="replace")
            data = json.loads(payload)
        except Exception as e:
            print(f"[camera:{self.camera_id}][mqtt] invalid json: {e}")
            return
        if not isinstance(data, dict):
            print(f"[camera:{self.camera_id}][mqtt] payload is not a JSON object")
            return

        target_timestamp = self._extract_event_timestamp(data)
        self.mqtt_buffer.append(BufferedMqttEvent(timestamp=target_timestamp, payload=data))

        if getattr(self, "analysis_mode", "matched_frame") == "periodic_frame":
            return

        self._run_event_analysis(data, target_timestamp)

    def _run_event_analysis(self, payload: Dict[str, Any], target_timestamp: datetime) -> bool:
        resolved = self._resolve_event_analysis_image(payload, target_timestamp)
        if resolved is None:
            return False

        image_b64, image_mime = resolved
        return self._analyze_and_save(image_b64, target_timestamp, image_mime=image_mime)

    def _resolve_event_analysis_image(
        self,
        payload: Dict[str, Any],
        target_timestamp: datetime,
    ) -> tuple[str, str] | None:
        analysis_mode = getattr(self, "analysis_mode", "matched_frame")
        if analysis_mode == "snapshot":
            snapshot = self._extract_snapshot_image(payload)
            if snapshot is None:
                print(f"[camera:{self.camera_id}][mqtt] payload did not contain a snapshot image")
            return snapshot

        matched_frame = self.get_hot_buffer_frame_at(target_timestamp)
        if matched_frame is None:
            print(f"[camera:{self.camera_id}][mqtt] no matching frame in hot buffer")
            return None

        frame_b64 = base64.b64encode(matched_frame.jpeg_bytes).decode("utf-8")
        return frame_b64, "image/jpeg"

    def _extract_snapshot_image(self, payload: Dict[str, Any]) -> tuple[str, str] | None:
        image = payload.get("image")
        if not isinstance(image, dict):
            return None

        data = image.get("data")
        if not isinstance(data, str) or not data.strip():
            return None

        image_mime = image.get("type")
        if not isinstance(image_mime, str) or "/" not in image_mime:
            image_mime = "image/jpeg"
        return data, image_mime

    def _query_analysis_client(self, image_b64: str, image_mime: str) -> Dict[str, Any]:
        if self.analysis_client is None:
            raise RuntimeError("analysis_client is not configured")

        if hasattr(self.analysis_client, "query_description_closed"):
            descriptors = getattr(self, "analysis_descriptors", list(DEFAULT_ANALYSIS_DESCRIPTORS))
            return self.analysis_client.query_description_closed(
                image_b64,
                descriptors,
                image_mime=image_mime,
            )

        if hasattr(self.analysis_client, "query_description_open"):
            return self.analysis_client.query_description_open(
                image_b64,
                image_mime=image_mime,
            )

        raise AttributeError(
            "analysis_client must implement query_description_closed() or query_description_open()"
        )

    def _extract_analysis_terms(self, response: Dict[str, Any]) -> List[str]:
        if not isinstance(response, dict):
            return []

        keywords = response.get("keywords")
        if isinstance(keywords, list):
            return [item.strip() for item in keywords if isinstance(item, str) and item.strip()]

        description = response.get("description")
        if isinstance(description, dict):
            nested_keywords = description.get("keywords")
            if isinstance(nested_keywords, list):
                return [
                    item.strip()
                    for item in nested_keywords
                    if isinstance(item, str) and item.strip()
                ]
            return []

        if isinstance(description, list):
            return [item.strip() for item in description if isinstance(item, str) and item.strip()]

        if isinstance(description, str) and description.strip():
            return [description.strip()]

        return []

    def _analyze_and_save(
        self,
        image_b64: str,
        created_at: datetime,
        *,
        image_mime: str = "image/jpeg",
    ) -> bool:
        if self.analysis_client is None:
            print(f"[camera:{self.camera_id}][mqtt] analysis_client is not configured")
            return False

        try:
            analysis_response = self._query_analysis_client(image_b64, image_mime)
            analysis_terms = self._extract_analysis_terms(analysis_response)
            if not analysis_terms:
                print(f"[camera:{self.camera_id}][mqtt] analysis returned no searchable terms")
                return False
            save_analysis(
                created_at=created_at,
                description=analysis_terms,
            )
            return True
        except Exception as e:
            print(f"[camera:{self.camera_id}][mqtt] analysis/save failed: {e}")
            return False

    def _periodic_analysis_loop(self) -> None:
        while not self._analysis_stop_event.is_set():
            self.run_periodic_analysis_once()
            self._analysis_stop_event.wait(self.analysis_interval_seconds)

    def configure_periodic_analysis_from_duration(self, total_duration_seconds: float) -> float:
        self.analysis_interval_seconds = calculate_adaptive_analysis_interval_seconds(
            total_duration_seconds,
            target_samples=self.analysis_target_samples,
            min_interval_seconds=self.min_analysis_interval_seconds,
        )
        return self.analysis_interval_seconds

    def _extract_event_timestamp(self, payload: Dict[str, Any]) -> datetime:
        start_time = payload.get("start_time")
        if isinstance(start_time, str) and start_time.strip():
            try:
                return datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            except ValueError:
                print(f"[camera:{self.camera_id}][mqtt] invalid start_time format: {start_time}")

        return datetime.now(timezone.utc)

    def run_periodic_analysis_once(self) -> bool:
        if getattr(self, "analysis_mode", "matched_frame") != "periodic_frame":
            return False

        latest_frame = self.get_latest_hot_buffer_frame()
        if latest_frame is None:
            return False

        last_analysis_timestamp = getattr(self, "_last_periodic_analysis_timestamp", None)
        if (
            last_analysis_timestamp is not None
            and latest_frame.timestamp <= last_analysis_timestamp
        ):
            return False

        self._last_periodic_analysis_timestamp = latest_frame.timestamp
        frame_b64 = base64.b64encode(latest_frame.jpeg_bytes).decode("utf-8")
        return self._analyze_and_save(
            frame_b64,
            latest_frame.timestamp,
            image_mime="image/jpeg",
        )

    def init_buffer(self) -> None:
        max_frames = self.hot_buffer_seconds * self.hot_buffer_fps
        self.frame_buffer = FrameRingBuffer(
            max_frames=max_frames,
            max_bytes=self.hot_buffer_max_bytes,
        )
        self._buffer_stop_event.clear()
        self._buffer_thread = threading.Thread(
            target=self._buffer_loop,
            name=f"camera-{self.camera_id}-hot-buffer",
            daemon=True,
        )
        self._buffer_thread.start()

    def _buffer_loop(self) -> None:
        frame_interval = 1.0 / float(self.hot_buffer_fps)
        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), int(self.hot_buffer_jpeg_quality)]

        while not self._buffer_stop_event.is_set():
            capture = cv2.VideoCapture(self.rtsp_url)
            if not capture.isOpened():
                print(f"[camera:{self.camera_id}][buffer] RTSP open failed, retrying...")
                time.sleep(1.0)
                continue

            next_capture_ts = time.monotonic()

            while not self._buffer_stop_event.is_set():
                ok, frame = capture.read()
                if not ok or frame is None:
                    print(f"[camera:{self.camera_id}][buffer] RTSP read failed, reconnecting...")
                    break

                now = time.monotonic()
                if now < next_capture_ts:
                    continue
                next_capture_ts = now + frame_interval

                h, w = frame.shape[:2]
                if self.hot_buffer_max_width > 0 and w > self.hot_buffer_max_width:
                    new_h = int(h * (self.hot_buffer_max_width / float(w)))
                    frame = cv2.resize(
                        frame,
                        (self.hot_buffer_max_width, new_h),
                        interpolation=cv2.INTER_AREA,
                    )
                    h, w = frame.shape[:2]

                enc_ok, encoded = cv2.imencode(".jpg", frame, encode_params)
                if not enc_ok:
                    continue

                packet = BufferedFrame(
                    timestamp=datetime.now(timezone.utc),
                    jpeg_bytes=encoded.tobytes(),
                    width=w,
                    height=h,
                )
                if self.frame_buffer is not None:
                    self.frame_buffer.append(packet)

            capture.release()
            if not self._buffer_stop_event.is_set():
                time.sleep(0.3)

    def get_hot_buffer_frames(self, seconds: int | None = None) -> List[BufferedFrame]:
        if self.frame_buffer is None:
            return []
        window = seconds if seconds is not None else self.hot_buffer_seconds
        return self.frame_buffer.latest(window)

    def get_hot_buffer_frame_at(self, target_timestamp: datetime) -> BufferedFrame | None:
        if self.frame_buffer is None:
            return None
        return self.frame_buffer.search_frame(target_timestamp)

    def get_latest_hot_buffer_frame(self) -> BufferedFrame | None:
        frames = self.get_hot_buffer_frames()
        if not frames:
            return None
        return frames[-1]

    def get_mqtt_event_at(
        self,
        target_timestamp: datetime,
        tolerance_ms: Optional[int] = None,
    ) -> Optional[BufferedMqttEvent]:
        return self.mqtt_buffer.search_event(target_timestamp, tolerance_ms=tolerance_ms)

    def get_context_at(
        self,
        target_timestamp: datetime,
        tolerance_ms: Optional[int] = 500,
    ) -> Dict[str, Any]:
        frame = self.get_hot_buffer_frame_at(target_timestamp)
        mqtt_event = self.get_mqtt_event_at(target_timestamp, tolerance_ms=tolerance_ms)
        return {
            "target_timestamp": target_timestamp,
            "frame": frame,
            "mqtt_event": mqtt_event,
            "frame_found": frame is not None,
            "mqtt_found": mqtt_event is not None,
        }

    def hot_buffer_stats(self) -> Dict[str, int]:
        if self.frame_buffer is None:
            return {"frames": 0, "bytes": 0, "max_frames": 0, "max_bytes": 0}
        return self.frame_buffer.stats()

    def mqtt_buffer_stats(self) -> Dict[str, int]:
        return self.mqtt_buffer.stats()

#för testning av RTSP data (frames)
    def dump_latest_hot_buffer_frame(self, output_path: str = "debug_latest.jpg") -> bool:
        frames = self.get_hot_buffer_frames(5)
        if not frames:
            print(f"[camera:{self.camera_id}][buffer] no frames to dump")
            return False

        latest = frames[-1]
        with open(output_path, "wb") as f:
            f.write(latest.jpeg_bytes)

        print(
            f"[camera:{self.camera_id}][buffer] wrote {output_path} "
            f"ts={latest.timestamp.isoformat()} size={latest.width}x{latest.height} "
            f"bytes={len(latest.jpeg_bytes)}"
        )
        return True

    def stop_recording(self) -> None:
        analysis_stop_event = getattr(self, "_analysis_stop_event", None)
        if analysis_stop_event is not None:
            analysis_stop_event.set()
        if getattr(self, "_analysis_thread", None) is not None:
            self._analysis_thread.join(timeout=2.0)
            self._analysis_thread = None

        buffer_stop_event = getattr(self, "_buffer_stop_event", None)
        if buffer_stop_event is not None:
            buffer_stop_event.set()
        if getattr(self, "_buffer_thread", None) is not None:
            self._buffer_thread.join(timeout=2.0)
            self._buffer_thread = None

        if getattr(self, "mqtt_client", None) is not None:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()

        stop_recording(getattr(self, "recording_process", None))
        self.recording_process = None


def main() -> None:
    from analysis.sync_prisma import LLMClientSync

    load_dotenv()
    camera_ip = "192.168.0.90"
    username = "student"
    password = "student"
    rtsp_url = f"rtsp://{username}:{password}@{camera_ip}/axis-media/media.amp"
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    broker_host = "10.255.255.1"
    broker_port = 1883
    
    endpoint = "https://api.ai.auth.axis.cloud/v1/chat/completions"
    api_key = os.environ.get("FACADE_API_KEY")
    model = "prisma_gemini_pro"

    llm = LLMClientSync(endpoint, api_key, model)

    camera = Camera("1", rtsp_url, ffmpeg, broker_host, broker_port,analysis_client=llm, segment_seconds=10)
    
    time.sleep(60)
    #print("Hot buffer stats:", camera.hot_buffer_stats())
    #camera.dump_latest_hot_buffer_frame("debug_latest.jpg")

    camera.stop_recording()


if __name__ == "__main__":
    main()
