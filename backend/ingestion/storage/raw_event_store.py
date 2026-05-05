# ingestion_/storage/raw_event_store.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from ingestion.source.replay_reader import RawEvent


class RawEventStore:
    """Valfri lagring av rådata (för replay/debug), INTE databasen.

    (Används i största syfte för testning)
    """
    def __init__(
        self,
        folder: str = "replay_out",
        file_name: str = "raw_events.jsonl",
        output_path: Optional[str | Path] = None,
    ) -> None:
        if output_path is not None:
            output = Path(output_path)
            self.base = output.parent
            self.file = output
        else:
            self.base = Path(folder)
            self.file = self.base / file_name
        self.base.mkdir(parents=True, exist_ok=True)

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
