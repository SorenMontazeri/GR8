# ingestion_/queue/event_buffer.py
from __future__ import annotations

from dataclasses import dataclass
from queue import Queue, Empty
from typing import Generic, Optional, TypeVar


T = TypeVar("T")


class EventBuffer(Generic[T]):
    """En enkel wrapper runt Queue för att göra den lättare att mocka/testa."""
    def __init__(self, maxsize: int = 0) -> None:
        self._q: Queue[T] = Queue(maxsize=maxsize)

    def put(self, item: T, block: bool = True, timeout: Optional[float] = None) -> None:
        self._q.put(item, block=block, timeout=timeout)

    def get(self, block: bool = True, timeout: Optional[float] = None) -> T:
        return self._q.get(block=block, timeout=timeout)

    def empty(self) -> bool:
        return self._q.empty()

    def qsize(self) -> int:
        return self._q.qsize()

    def try_get(self) -> Optional[T]:
        try:
            return self._q.get(block=False)
        except Empty:
            return None