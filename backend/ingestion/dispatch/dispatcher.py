from __future__ import annotations

from typing import Callable, Generic, Protocol, TypeVar


T = TypeVar("T")


class Dispatcher(Protocol[T]):
    """Gemensamt kontrakt för hur mappade events skickas vidare."""
    def dispatch(self, item: T) -> None:
        ...


class DirectDispatcher(Generic[T]):
    """Direkt synkron dispatch till nästa steg i pipelinen."""
    def __init__(self, handler: Callable[[T], None]) -> None:
        self._handler = handler

    def dispatch(self, item: T) -> None:
        self._handler(item)
