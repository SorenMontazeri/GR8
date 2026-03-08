from __future__ import annotations

import json
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Deque, Dict, Optional


@dataclass(frozen=True)
class BufferedMqttEvent:
    timestamp: datetime
    payload: Dict[str, Any]


class MqttEventRingBuffer:
    """Liten, trådsäker ringbuffer för MQTT-event."""

    def __init__(self, max_events: int = 300, max_bytes: int = 5 * 1024 * 1024) -> None:
        self._events: Deque[BufferedMqttEvent] = deque()
        self._max_events = max_events
        self._max_bytes = max_bytes
        self._total_bytes = 0
        self._lock = threading.Lock()

    def append(self, event: BufferedMqttEvent) -> None:
        approx_size = len(json.dumps(event.payload, ensure_ascii=False).encode("utf-8"))
        with self._lock:
            self._events.append(event)
            self._total_bytes += approx_size
            self._trim_locked()

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {
                "events": len(self._events),
                "bytes": self._total_bytes,
                "max_events": self._max_events,
                "max_bytes": self._max_bytes,
            }

    def search_event(
        self,
        target_timestamp: datetime,
        tolerance_ms: Optional[int] = None,
    ) -> Optional[BufferedMqttEvent]:
        with self._lock:
            if not self._events:
                return None
            events = list(self._events)

        lo = 0
        hi = len(events) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            mid_ts = events[mid].timestamp
            if mid_ts < target_timestamp:
                lo = mid + 1
            elif mid_ts > target_timestamp:
                hi = mid - 1
            else:
                candidate = events[mid]
                return self._within_tolerance(candidate, target_timestamp, tolerance_ms)

        if hi < 0:
            candidate = events[0]
        elif lo >= len(events):
            candidate = events[-1]
        else:
            before = events[hi]
            after = events[lo]
            candidate = before if (target_timestamp - before.timestamp) <= (after.timestamp - target_timestamp) else after

        return self._within_tolerance(candidate, target_timestamp, tolerance_ms)

    def _within_tolerance(
        self,
        candidate: BufferedMqttEvent,
        target_timestamp: datetime,
        tolerance_ms: Optional[int],
    ) -> Optional[BufferedMqttEvent]:
        if tolerance_ms is None:
            return candidate
        delta_ms = abs((candidate.timestamp - target_timestamp).total_seconds() * 1000.0)
        return candidate if delta_ms <= tolerance_ms else None

    def _trim_locked(self) -> None:
        while self._events and (
            len(self._events) > self._max_events or self._total_bytes > self._max_bytes
        ):
            old = self._events.popleft()
            self._total_bytes -= len(json.dumps(old.payload, ensure_ascii=False).encode("utf-8"))
