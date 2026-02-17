# ingestion_/storage/raw_event_store.py
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime

from dataTesting.source.replay_reader import RawEvent


class RawEventStore:
    """Valfri lagring av rådata (för replay/debug), INTE databasen.

    Ni sa att ni inte vill ha raw log till DB — så detta är bara filbaserat.
    """
    def __init__(self, folder: str = "replay_out") -> None:
        self.base = Path(folder)
        self.base.mkdir(parents=True, exist_ok=True)
        self.file = self.base / "raw_events.jsonl"

    def append(self, raw_event: RawEvent) -> None:
        row: Dict[str, Any] = {
            "received_at": raw_event.received_at.isoformat(),
            "source": raw_event.source,
            "replay_seq": raw_event.replay_seq,
            "replay_file": raw_event.replay_file,
            "raw": raw_event.raw,
        }
        with self.file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")