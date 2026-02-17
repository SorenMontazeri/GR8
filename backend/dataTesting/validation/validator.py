#validator: undersöka att data inte är trasig/tom
# ingestion_/validation/validator.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional, Tuple

from dataTesting.source.replay_reader import RawEvent


EventKind = Literal["object_track", "frame", "unknown"]


@dataclass(frozen=True)
class ValidatedEvent:
    """Validerat payload + vad det är för typ."""
    kind: EventKind
    payload: Dict[str, Any]
    # Om vi vill hålla kvar lite metadata från RawEvent:
    source: Literal["live", "replay"]
    replay_seq: Optional[int] = None
    replay_file: Optional[str] = None


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    event: Optional[ValidatedEvent] = None
    error: Optional[str] = None


def _guess_kind(payload: Dict[str, Any]) -> EventKind:
    """Liten heuristik för att skilja object_track vs frame.

    Axis kan ha olika wrapper-strukturer. Vi försöker vara toleranta i början.
    """
    # Vanligt: payload innehåller "start_time/end_time/duration/classes/path/parts/image"
    if any(k in payload for k in ("start_time", "end_time", "duration", "classes", "path", "parts")):
        return "object_track"

    # Frame-liknande: ibland finns "timestamp" + "image"/"frame"
    if "timestamp" in payload and ("image" in payload or "frame" in payload):
        return "frame"

    return "unknown"


def validate_raw_event(raw_event: RawEvent) -> ValidationResult:
    """Minimivalidering (AC02):
    - payload måste vara dict
    - ska inte vara tom
    - flagga/logga invalid utan crash
    """
    payload = raw_event.raw

    if not isinstance(payload, dict):
        return ValidationResult(ok=False, error="Raw event is not a JSON object (dict).")

    if not payload:
        return ValidationResult(ok=False, error="Raw event is empty JSON object.")

    # Minimalt: försök hitta "track id" / "channel_id" om det verkar vara object_track
    kind = _guess_kind(payload)

    # Extra mjuka checks (kan skärpas senare när ni vet schema)
    if kind == "object_track":
        if "id" not in payload:
            # i consolidated data kan det heta trackId etc. -> vi låter det passera men markerar
            # som "unknown" om det saknar id
            kind = "unknown"

    ve = ValidatedEvent(
        kind=kind,
        payload=payload,
        source="replay" if raw_event.source == "replay" else "live",
        replay_seq=raw_event.replay_seq,
        replay_file=raw_event.replay_file,
    )
    return ValidationResult(ok=True, event=ve)