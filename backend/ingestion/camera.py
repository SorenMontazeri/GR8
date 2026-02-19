from __future__ import annotations

import json
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Deque, Dict, List

import cv2
import imageio_ffmpeg
import paho.mqtt.client as mqtt

from ingestion.ingestion_service import IngestionService
from ingestion.record_ffmpeg import start_recording_ffmpeg, stop_recording
from ingestion.source.replay_reader import RawEvent


@dataclass(frozen=True)
class BufferedFrame:
    timestamp: datetime
    jpeg_bytes: bytes
    width: int
    height: int


class FrameRingBuffer:
    """Fast storlek + minnesbudget för hot buffer."""

    def __init__(self, max_frames: int, max_bytes: int) -> None:
        self._frames: Deque[BufferedFrame] = deque()
        self._max_frames = max_frames
        self._max_bytes = max_bytes
        self._total_bytes = 0
        self._lock = threading.Lock()

    def append(self, frame: BufferedFrame) -> None:
        with self._lock:
            self._frames.append(frame)
            self._total_bytes += len(frame.jpeg_bytes)
            self._trim_locked()

    def latest(self, seconds: int) -> List[BufferedFrame]:
        if seconds <= 0:
            return []
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=seconds)
        with self._lock:
            return [f for f in self._frames if f.timestamp >= cutoff]

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {
                "frames": len(self._frames),
                "bytes": self._total_bytes,
                "max_frames": self._max_frames,
                "max_bytes": self._max_bytes,
            }

    def _trim_locked(self) -> None:
        while self._frames and (
            len(self._frames) > self._max_frames or self._total_bytes > self._max_bytes
        ):
            old = self._frames.popleft()
            self._total_bytes -= len(old.jpeg_bytes)


class Camera:
    def __init__(
        self,
        camera_id: str,
        rtsp_url: str,
        ffmpeg: str,
        broker_host: str,
        broker_port: int,
        segment_seconds: int = 10,
        hot_buffer_seconds: int = 30,
        hot_buffer_fps: int = 5,
        hot_buffer_max_bytes: int = 50 * 1024 * 1024,
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
        self.hot_buffer_jpeg_quality = hot_buffer_jpeg_quality
        self.hot_buffer_max_width = hot_buffer_max_width

        self.frame_buffer: FrameRingBuffer | None = None
        self._buffer_stop_event = threading.Event()
        self._buffer_thread: threading.Thread | None = None
        self.ingestion_service = IngestionService()

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

        raw_event = RawEvent(
            raw=data,
            received_at=datetime.now(timezone.utc),
            source="live",
            replay_seq=None,
            replay_file=None,
        )
        ok = self.ingestion_service.handle_raw_event(raw_event)
        if not ok:
            print(f"[camera:{self.camera_id}][mqtt] event skipped/invalid")

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

    def hot_buffer_stats(self) -> Dict[str, int]:
        if self.frame_buffer is None:
            return {"frames": 0, "bytes": 0, "max_frames": 0, "max_bytes": 0}
        return self.frame_buffer.stats()

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

    camera = Camera("1", rtsp_url, ffmpeg, broker_host, broker_port, segment_seconds=5)
    time.sleep(7)
    print("Hot buffer stats:", camera.hot_buffer_stats())
    camera.stop_recording()


if __name__ == "__main__":
    main()
