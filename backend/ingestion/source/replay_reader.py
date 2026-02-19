#replay reader: kunna läsa och spotta ut RawEvent på sama sätt som live hade gjort
# ingestion_/source/replay_reader.py
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, Literal, Optional, Union
from datetime import datetime, timezone


SourceType = Literal["live", "replay"]


@dataclass(frozen=True)
class RawEvent:
    """Råhändelse (precis som den kommer från fil/MQTT), före validering/normalisering."""
    raw: Dict[str, Any]
    received_at: datetime
    source: SourceType = "replay"
    # Hjälpfält ifall vi vill debugga replay och veta vilken rad/post som kom
    replay_seq: Optional[int] = None
    replay_file: Optional[str] = None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _load_json_any(path: Path) -> Any:
    # Stöd: 1) JSONL (en json per rad), 2) single JSON object, 3) JSON array
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []

    # JSONL detection: om första icke-whitespace inte är '{' eller '[' -> fortfarande kan vara JSONL,
    # men enklast: om flera rader och varje rad ser ut som JSON-object
    if "\n" in text:
        # prova JSONL först
        rows = [r.strip() for r in text.splitlines() if r.strip()]
        jsonl_ok = True
        parsed_rows = []
        for r in rows:
            try:
                obj = json.loads(r)
                parsed_rows.append(obj)
            except Exception:
                jsonl_ok = False
                break
        if jsonl_ok:
            return parsed_rows

    # annars: prova standard JSON (object eller array)
    return json.loads(text)


def iter_replay_events(file_path: Union[str, Path]) -> Iterator[RawEvent]:
    """Läser replay-data och yieldar RawEvent i ordning.

    Accepterar:
    - JSONL: en JSON per rad
    - JSON array: [ {...}, {...} ]
    - JSON object: { ... } (yieldar en enda händelse)
    """
    path = Path(file_path)
    data = _load_json_any(path)

    def emit(obj: Any, seq: int) -> Optional[RawEvent]:
        if not isinstance(obj, dict):
            return None
        return RawEvent(
            raw=obj,
            received_at=_now_utc(),
            source="replay",
            replay_seq=seq,
            replay_file=str(path),
        )

    if isinstance(data, list):
        for i, item in enumerate(data, start=1):
            ev = emit(item, i)
            if ev:
                yield ev
    elif isinstance(data, dict):
        ev = emit(data, 1)
        if ev:
            yield ev
    else:
        # Okänt format, yieldar ingenting
        return
