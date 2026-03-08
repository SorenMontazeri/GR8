from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Deque, Dict, List


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

    def search_frame(self, target_timestamp: datetime) -> BufferedFrame | None:
        with self._lock:
            if not self._frames:
                return None
            frames = list(self._frames)

        lo = 0
        hi = len(frames) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            mid_ts = frames[mid].timestamp
            if mid_ts < target_timestamp:
                lo = mid + 1
            elif mid_ts > target_timestamp:
                hi = mid - 1
            else:
                return frames[mid]

        if hi < 0:
            return frames[0]
        if lo >= len(frames):
            return frames[-1]

        before = frames[hi]
        after = frames[lo]
        if (target_timestamp - before.timestamp) <= (after.timestamp - target_timestamp):
            return before
        return after
