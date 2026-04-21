from __future__ import annotations
import base64
import json
from pathlib import Path
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import os
import asyncio
import numpy as np

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - optional in thin test envs
    def load_dotenv() -> bool:
        return False


import cv2
import imageio_ffmpeg
import paho.mqtt.client as mqtt

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.database import save_description_bundle
from ingestion.buffers.mqtt_event_buffer import BufferedMqttEvent, MqttEventRingBuffer
from ingestion.buffers.rtsp_hot_buffer import BufferedFrame, FrameRingBuffer
from ingestion.record_ffmpeg import start_recording_ffmpeg, stop_recording

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
        enable_recording: bool = True,
        hot_buffer_seconds: int = 30,
        hot_buffer_fps: int = 5,
        hot_buffer_max_bytes: int = 50 * 1024 * 1024, #TODO increase max bytes if needed
        mqtt_buffer_max_events: int = 300,
        mqtt_buffer_max_bytes: int = 5 * 1024 * 1024,
        hot_buffer_jpeg_quality: int = 70,
        hot_buffer_max_width: int = 960,
    ) -> None:
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

        self.frame_buffer: FrameRingBuffer | None = None
        self.mqtt_buffer = MqttEventRingBuffer(
            max_events=self.mqtt_buffer_max_events,
            max_bytes=self.mqtt_buffer_max_bytes,
        )
        self._buffer_stop_event = threading.Event()
        self._buffer_thread: threading.Thread | None = None
        self.analysis_client = analysis_client

        # Fix for asyncio
        self._async_loop = asyncio.new_event_loop()
        self._async_thread: threading.Thread | None = None
        self._async_loop_ready = threading.Event()
        self.init_async_loop()

        if enable_recording:
            self.init_recording(ffmpeg, segment_seconds)
        self.init_buffer()
        self.init_mqtt(broker_host, broker_port)

    def init_recording(self, ffmpeg: str, segment_seconds: int) -> None:
        self.recording_process = start_recording_ffmpeg(
            ffmpeg, self.rtsp_url, self.camera_id, segment_seconds
        )

    def init_mqtt(self, broker_host: str, broker_port: int) -> None:
        self.mqtt_client.connect(broker_host, broker_port, 60)
        self.mqtt_client.on_message = self.on_message
        self.mqtt_client.subscribe(f"camera/{self.camera_id}")
        self.mqtt_client.loop_start()

    def init_async_loop(self) -> None:
        self._async_thread = threading.Thread(
            target=self._async_loop_thread_main,
            name=f"camera-{self.camera_id}-async-loop",
            daemon=True,
        )
        self._async_thread.start()

        if not self._async_loop_ready.wait(timeout=5.0):
            raise RuntimeError(f"[camera:{self.camera_id}] async loop failed to start")

    def _async_loop_thread_main(self) -> None:
        asyncio.set_event_loop(self._async_loop)
        self._async_loop_ready.set()
        self._async_loop.run_forever()

    async def _run_analysis(
        self,
        snapshot_b64: str,
        full_frame_b64: str,
        selection_1_images: list[str],
        selection_2_images: list[str],
    ) -> tuple[Any, Any, Any, Any]:
        return await asyncio.gather(
            self.analysis_client.query_description_open([snapshot_b64]),
            self.analysis_client.query_description_open([full_frame_b64]),
            self.analysis_client.query_description_open(selection_1_images),
            self.analysis_client.query_description_open(selection_2_images),
        )

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
                
                
        # Get necessary info
        target_start_time = self._extract_event_timestamp(data)
        target_end_time = self._extract_event_end_time(data)
        image = data.get("image")
        snapshot_b64 = image.get("data") if isinstance(image, dict) else None
        if snapshot_b64 is None:
            print(f"[camera:{self.camera_id}] missing mqtt snapshot")
            return


        matched_full_frame = self.get_hot_buffer_frame_at(target_start_time)
        if matched_full_frame is None:
                print(f"[camera:{self.camera_id}] no matching frame in hot buffer")
                return
        full_frame_b64 = base64.b64encode(matched_full_frame.jpeg_bytes).decode("utf-8")

        selection_1_images, selection_1_timestamps =  self.frame_selection_1(target_start_time, target_end_time)
        selection_2_images, selection_2_timestamps =  self.frame_selection_2(target_start_time, target_end_time, 90)

        # Temporary solution for short consolodated, might have to prune short consolidated
        if not selection_1_images and not selection_1_timestamps:
            selection_1_images = [full_frame_b64]
            selection_1_timestamps = [target_start_time]

        if not selection_2_images and not selection_2_timestamps:
            selection_2_images = [full_frame_b64]
            selection_2_timestamps = [target_start_time]


        try:
            future = asyncio.run_coroutine_threadsafe(
                self._run_analysis(
                    snapshot_b64=snapshot_b64,
                    full_frame_b64=full_frame_b64,
                    selection_1_images=selection_1_images,
                    selection_2_images=selection_2_images,
                ),
                self._async_loop,
            )
            response_snapshot, response_full_frame, response_selection_1, response_selection_2 = future.result(timeout=60)

        except Exception as exc:
            print(f"[camera:{self.camera_id}] analysis failed: {exc}")
            return
        
        print(response_snapshot)
        print(response_full_frame)
        print(response_selection_1)
        print(response_selection_2)

        try:
            save_description_bundle(
                target_start_time,
                target_end_time,
                datetime.now(timezone.utc),
                response_selection_1["description"],
                response_selection_2["description"],
                response_snapshot["description"],
                response_full_frame["description"],
                selection_1_timestamps,
                selection_2_timestamps,
                selection_1_images,
                selection_2_images,
                target_start_time,
                matched_full_frame.timestamp,
                snapshot_b64,
                full_frame_b64,
            )
        except Exception as exc:
            print(f"[camera:{self.camera_id}] saving to database failed: {exc}")


    def _extract_event_timestamp(self, payload: Dict[str, Any]) -> datetime:
        start_time = payload.get("start_time")
        if isinstance(start_time, str) and start_time.strip():
            try:
                parsed = datetime.fromisoformat(start_time.strip().replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc)
            except ValueError:
                print(f"[camera:{self.camera_id}][mqtt] invalid start_time format: {start_time}")

        return datetime.now(timezone.utc)
    
    def _extract_event_end_time(self, payload: Dict[str, Any]) -> datetime:
        end_time = payload.get("end_time")
        if isinstance(end_time, str) and end_time.strip():
            try:
                parsed = datetime.fromisoformat(end_time.strip().replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc)
            except ValueError:
                print(f"[camera:{self.camera_id}][mqtt] invalid start_time format: {end_time}")

        return datetime.now(timezone.utc)

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

    def frame_selection_1(self, start_time: datetime, end_time: datetime) -> tuple[list[str], list[datetime]]:
        if end_time < start_time:
            return [], []

        def encode_frame(frame: BufferedFrame) -> str:
            return base64.b64encode(frame.jpeg_bytes).decode("utf-8")

        if self.frame_buffer is None:
            return [], []

        duration = (end_time - start_time).total_seconds()
        frame_count = 1 if duration <= 1 else min(int(duration), max(5, int(duration / 3)))

        if frame_count <= 0:
            return [], []

        selected_frames: list[str] = []
        selected_timestamps: list[datetime] = []
        seen: set[bytes] = set()
        step = timedelta(0) if frame_count == 1 else (end_time - start_time) / (frame_count - 1)

        for i in range(frame_count):
            frame = self.get_hot_buffer_frame_at(start_time + step * i)
            if frame is None or frame.timestamp < start_time or frame.timestamp > end_time:
                continue
            if frame.jpeg_bytes in seen:
                continue
            seen.add(frame.jpeg_bytes)
            selected_frames.append(encode_frame(frame))
            selected_timestamps.append(frame.timestamp)

        return selected_frames, selected_timestamps
    
    def frame_selection_2(self, start_time: datetime, end_time: datetime, max_change_percent: float, max_interval_seconds: int = 10) -> tuple[list[str], list[datetime]]:
        

        if end_time < start_time or max_change_percent < 0 or max_interval_seconds <= 0:
            return [], []

        def thumbnail(frame: BufferedFrame):
            image = cv2.imdecode(np.frombuffer(frame.jpeg_bytes, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
            resized_image = cv2.resize(image, (max(1, frame.width // 8), max(1, frame.height // 8)), interpolation=cv2.INTER_AREA)
            return cv2.GaussianBlur(resized_image, (3, 3), 0)

        def changed_pixel_ratio(left, right) -> float:
            pixel_threshold = 12
            diff = cv2.absdiff(left, right)
            return float((diff > pixel_threshold).sum()) * 100.0 / float(diff.size)

        def encode_frame(frame: BufferedFrame) -> str:
            return base64.b64encode(frame.jpeg_bytes).decode("utf-8")

        if self.frame_buffer is None:
            return [], []

        with self.frame_buffer._lock:
            buffer_frames = [
                frame for frame in self.frame_buffer._frames if start_time <= frame.timestamp <= end_time
            ]

        if not buffer_frames:
            return [], []
        

        selected_frames = [encode_frame(buffer_frames[0])]
        selected_timestamps = [buffer_frames[0].timestamp]
        current_frame = buffer_frames[0]
        
        for next_frame in buffer_frames[1:]:
            change_percent = changed_pixel_ratio(thumbnail(current_frame), thumbnail(next_frame))
            if change_percent > max_change_percent and next_frame.timestamp < current_frame.timestamp + timedelta(seconds=max_interval_seconds):
                continue

            selected_frames.append(encode_frame(next_frame))
            selected_timestamps.append(next_frame.timestamp)
            current_frame = next_frame

        return selected_frames, selected_timestamps

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
        self._buffer_stop_event.set()
        if self._buffer_thread is not None:
            self._buffer_thread.join(timeout=2.0)
            self._buffer_thread = None

        self.mqtt_client.loop_stop()
        self.mqtt_client.disconnect()

        stop_recording(self.recording_process)
        self.recording_process = None


def main() -> None:
    from analysis.sync_prisma import LLMClientSync
    from analysis.async_prisma import LLMClient

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

    llm = LLMClient(endpoint, api_key, model)

    camera = Camera("1", rtsp_url, ffmpeg, broker_host, broker_port,analysis_client=llm, segment_seconds=10)
    
    time.sleep(60)
    #print("Hot buffer stats:", camera.hot_buffer_stats())
    #camera.dump_latest_hot_buffer_frame("debug_latest.jpg")

    camera.stop_recording()


if __name__ == "__main__":
    main()
