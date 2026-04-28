from __future__ import annotations

import base64
from datetime import datetime, timedelta
from typing import List, Tuple

import cv2
import numpy as np

from ingestion.buffers.rtsp_hot_buffer import BufferedFrame, FrameRingBuffer


def encode_frame(frame: BufferedFrame) -> str:
    return base64.b64encode(frame.jpeg_bytes).decode("utf-8")


def frame_selection_uniform(
    frame_buffer: FrameRingBuffer | None,
    start_time: datetime,
    end_time: datetime,
) -> Tuple[List[str], List[datetime]]:
    """
    Select frames evenly spaced between start_time and end_time.
    Deduplicates identical JPEG frames.
    """
    if frame_buffer is None or end_time < start_time:
        return [], []

    duration = (end_time - start_time).total_seconds()
    frame_count = 1 if duration <= 1 else min(int(duration), max(5, int(duration / 3)))

    if frame_count <= 0:
        return [], []

    selected_frames: List[str] = []
    selected_timestamps: List[datetime] = []
    seen: set[bytes] = set()

    step = timedelta(0) if frame_count == 1 else (end_time - start_time) / (frame_count - 1)

    for i in range(frame_count):
        frame = frame_buffer.search_frame(start_time + step * i)
        if frame is None:
            continue
        if not (start_time < frame.timestamp < end_time):
            continue
        if frame.jpeg_bytes in seen:
            continue

        seen.add(frame.jpeg_bytes)
        selected_frames.append(encode_frame(frame))
        selected_timestamps.append(frame.timestamp)

    return selected_frames, selected_timestamps


# -------------------------------------------------------------------
# Change-based frame selection
# -------------------------------------------------------------------

def _thumbnail(frame: BufferedFrame) -> np.ndarray:
    image = cv2.imdecode(
        np.frombuffer(frame.jpeg_bytes, dtype=np.uint8),
        cv2.IMREAD_GRAYSCALE,
    )
    resized = cv2.resize(
        image,
        (max(1, frame.width // 8), max(1, frame.height // 8)),
        interpolation=cv2.INTER_AREA,
    )
    return cv2.GaussianBlur(resized, (3, 3), 0)


def _changed_pixel_ratio(left: np.ndarray, right: np.ndarray) -> float:
    pixel_threshold = 12
    diff = cv2.absdiff(left, right)
    return float((diff > pixel_threshold).sum()) * 100.0 / float(diff.size)


def frame_selection_movement(
    frame_buffer: FrameRingBuffer | None,
    start_time: datetime,
    end_time: datetime,
    max_change_percent: float,
    max_interval_seconds: int = 10,
) -> Tuple[List[str], List[datetime]]:
    """
    Select frames based on visual change percentage.
    Ensures minimum temporal spacing.
    """
    if (
        frame_buffer is None
        or end_time < start_time
        or max_change_percent < 0
        or max_interval_seconds <= 0
    ):
        return [], []

    with frame_buffer._lock:
        buffer_frames = [
            frame
            for frame in frame_buffer._frames
            if start_time <= frame.timestamp <= end_time
        ]

    if not buffer_frames:
        return [], []

    selected_frames = [encode_frame(buffer_frames[0])]
    selected_timestamps = [buffer_frames[0].timestamp]

    current_frame = buffer_frames[0]
    current_thumb = _thumbnail(current_frame)

    for next_frame in buffer_frames[1:]:
        next_thumb = _thumbnail(next_frame)
        change = _changed_pixel_ratio(current_thumb, next_thumb)

        if (change > max_change_percent and next_frame.timestamp < current_frame.timestamp + timedelta(seconds=max_interval_seconds)):
            continue

        selected_frames.append(encode_frame(next_frame))
        selected_timestamps.append(next_frame.timestamp)
        current_frame = next_frame
        current_thumb = next_thumb

    return selected_frames, selected_timestamps