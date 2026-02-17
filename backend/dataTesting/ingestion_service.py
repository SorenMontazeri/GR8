# ingestion_/ingestion_service.py
from __future__ import annotations

import uuid
from typing import Optional

from dataTesting.queue.event_buffer import EventBuffer
from dataTesting.source.replay_reader import iter_replay_events, RawEvent
from dataTesting.storage.raw_event_store import RawEventStore
from dataTesting.validation.validator import validate_raw_event
from dataTesting.normalization.mapper import transform_axis_payload_to_internal_event

from dataTesting.normalization.mapper import (
    InternalEvent,
    map_object_track_to_internal_event,
    SourceType,
)


class IngestionService:
    """Kopplar ihop ingestion-pipelinen:
    source -> validator -> mapper -> buffer -> (dispatch senare)

    Målet: live och replay ska trigga exakt samma logik (AC03).
    """
    def __init__(
        self,
        *,
        buffer: Optional[EventBuffer[InternalEvent]] = None,
        raw_store: Optional[RawEventStore] = None,
        enable_raw_store: bool = True,
    ) -> None:
        self.buffer = buffer or EventBuffer()
        self.raw_store = raw_store or RawEventStore()
        self.enable_raw_store = enable_raw_store

    def _next_event_id(self) -> str:
        return str(uuid.uuid4())

    def handle_raw_event(self, raw_event: RawEvent) -> bool:
        """En 'ingång' för både MQTT och replay."""
        # 1) validera
        res = validate_raw_event(raw_event)
        if not res.ok or res.event is None:
            # AC02: logga + flagga utan crash (här: print, byt senare mot logger)
            print(f"[ingestion][invalid] {res.error} replay_seq={raw_event.replay_seq}")
            return False

        # 2) (valfritt) spara rådata för replay/debug (FIL, ej DB)
        if self.enable_raw_store:
            try:
                self.raw_store.append(raw_event)
            except Exception as e:
                print(f"[ingestion][warn] raw_store append failed: {e}")

        # 3) mappa till InternalEvent om vi känner igen typen
        kind = res.event.kind
        if kind == "object_track":
            internal = transform_axis_payload_to_internal_event(
                src=res.event.payload,
                source="replay" if res.event.source == "replay" else "live",
                fallback_event_id=self._next_event_id(),
            )
            self.buffer.put(internal)
            return True

        # Om vi inte kan mappa ännu (t.ex. frame eller unknown), flagga men krascha inte
        print(f"[ingestion][skip] kind={kind} not mapped yet replay_seq={raw_event.replay_seq}")
        return False

    def run_replay(self, replay_file_path: str) -> int:
        """Kör en replay-fil igenom ingestion (AC03). Returnerar antal InternalEvents."""
        count = 0
        for raw_event in iter_replay_events(replay_file_path):
            ok = self.handle_raw_event(raw_event)
            if ok:
                count += 1
        return count