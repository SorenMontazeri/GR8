from __future__ import annotations
import base64
import json
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import cv2
import imageio_ffmpeg
import paho.mqtt.client as mqtt

from database.database import save_analysis
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

        matched_frame = self.get_hot_buffer_frame_at(target_timestamp)
        if matched_frame is None:
            print(f"[camera:{self.camera_id}][mqtt] no matching frame in hot buffer")
            return

        if self.analysis_client is None:
            print(f"[camera:{self.camera_id}][mqtt] analysis_client is not configured")
            return

        try:
            frame_b64 = base64.b64encode(matched_frame.jpeg_bytes).decode("utf-8")
            analysis_response = self.analysis_client.query_description_closed(
                frame_b64,
                ["white_clothes", "man", "woman", "gray_clothes", "green_clothes"],
                image_mime="image/jpeg",
            )
            description = analysis_response.get("description") if isinstance(analysis_response, dict) else None
            if not description:
                print(f"[camera:{self.camera_id}][mqtt] analysis returned no description")
                return
            save_analysis(
                created_at=target_timestamp,
                description=description["keywords"],
            )
        except Exception as e:
            print(f"[camera:{self.camera_id}][mqtt] analysis/save failed: {e}")

    def _extract_event_timestamp(self, payload: Dict[str, Any]) -> datetime:
        start_time = payload.get("start_time")
        if isinstance(start_time, str) and start_time.strip():
            try:
                return datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            except ValueError:
                print(f"[camera:{self.camera_id}][mqtt] invalid start_time format: {start_time}")
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
    camera_ip = "192.168.0.90"
    username = "student"
    password = "student"
    rtsp_url = f"rtsp://{username}:{password}@{camera_ip}/axis-media/media.amp"
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    broker_host = "10.255.255.1"
    broker_port = 1883

    camera = Camera("1", rtsp_url, ffmpeg, broker_host, broker_port, segment_seconds=20)
    
    time.sleep(10)
    print("Hot buffer stats:", camera.hot_buffer_stats())
    camera.dump_latest_hot_buffer_frame("debug_latest.jpg")

    camera.stop_recording()


if __name__ == "__main__":
    main()
