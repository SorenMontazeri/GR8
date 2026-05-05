from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

import cv2

from ingestion.buffers.rtsp_hot_buffer import BufferedFrame, FrameRingBuffer


class OpenCvHotBuffer:
    def __init__(
        self,
        rtsp_url: str,
        camera_id: str,
        seconds: int = 30,
        fps: int = 5,
        max_bytes: int = 50 * 1024 * 1024,
        jpeg_quality: int = 70,
        max_width: int = 960,
    ) -> None:
        self.rtsp_url = rtsp_url
        self.camera_id = str(camera_id)
        self.seconds = seconds
        self.fps = fps
        self.jpeg_quality = jpeg_quality
        self.max_width = max_width

        self._buffer = FrameRingBuffer(
            max_frames=seconds * fps,
            max_bytes=max_bytes,
        )
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._sample_count = 0

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run,
            name=f"camera-{self.camera_id}-opencv-hot-buffer",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    def latest(self, seconds: int | None = None) -> list[BufferedFrame]:
        window = seconds if seconds is not None else self.seconds
        return self._buffer.latest(window)

    def frame_at(self, timestamp: datetime) -> BufferedFrame | None:
        return self._buffer.frame_at(timestamp)

    def frames_between(self, start_time: datetime, end_time: datetime) -> list[BufferedFrame]:
        return self._buffer.frames_between(start_time, end_time)

    def stats(self) -> dict[str, int]:
        return self._buffer.stats()

    def _run(self) -> None:
        print(f"[camera:{self.camera_id}][hot-buffer][opencv] opening rtsp={self.rtsp_url}")
        cap = cv2.VideoCapture(self.rtsp_url)
        if not cap.isOpened():
            print(f"[camera:{self.camera_id}][hot-buffer][opencv] failed to open RTSP stream")
            return

        frame_interval = 1.0 / max(self.fps, 1)
        last_emit = 0.0

        try:
            while not self._stop_event.is_set():
                ok, frame = cap.read()
                if not ok or frame is None:
                    print(f"[camera:{self.camera_id}][hot-buffer][opencv] failed to read frame")
                    time.sleep(0.2)
                    continue

                now = time.monotonic()
                if now - last_emit < frame_interval:
                    continue
                last_emit = now

                height, width = frame.shape[:2]
                if self.max_width > 0 and width > self.max_width:
                    new_height = int(height * (self.max_width / float(width)))
                    frame = cv2.resize(frame, (self.max_width, new_height), interpolation=cv2.INTER_AREA)
                    height, width = frame.shape[:2]

                encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), int(self.jpeg_quality)]
                ok, encoded = cv2.imencode(".jpg", frame, encode_params)
                if not ok:
                    continue

                timestamp = datetime.now(timezone.utc)
                self._buffer.append(
                    BufferedFrame(
                        timestamp=timestamp,
                        jpeg_bytes=encoded.tobytes(),
                        width=width,
                        height=height,
                    )
                )
                self._sample_count += 1
                if self._sample_count <= 3 or self._sample_count % 50 == 0:
                    print(
                        f"[camera:{self.camera_id}][hot-buffer][opencv] sample={self._sample_count} "
                        f"ts={timestamp.isoformat()} size={width}x{height}"
                    )
        finally:
            cap.release()
