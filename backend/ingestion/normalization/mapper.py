"""normalization.mapper

Tar validerad Axis-data (t.ex. ObjectTrack) och mappar till en stabil intern datatyp.

Målet: resten av systemet ska kunna lita på InternalEvent oavsett om källan är live eller replay.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional


SourceType = Literal["live", "replay"]


@dataclass(frozen=True)
class InternalEvent:
    """Stabil, intern representation som skickas vidare till analys."""

    event_id: str
    track_id: str
    camera_id: str
    timestamp: datetime
    snapshot_ref: Optional[str]
    source: SourceType
    payload: Dict[str, Any]
    event_type: Literal["object_track", "frame"] = "object_track"


def parse_axis_timestamp(value: Any) -> datetime:
    """Parsar Axis-tidsträngar.

    Axis-dokumentationen använder ISO-liknande strängar. Vi försöker vara toleranta:
    - 'Z' -> UTC
    - utan timezone -> antas UTC
    """
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        # Fallback: om vi inte har en timestamp, sätt nu (UTC)
        return datetime.now(timezone.utc)

    s = value.strip()
    # Vanlig variant: 2025-01-01T12:34:56Z
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        # Sista utväg: returnera "nu" för att inte krascha ingestion
        return datetime.now(timezone.utc)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt

def extract_track_id(payload: Dict[str, Any]) -> str:
    # Primärt: Axis object track-id brukar ligga i "id"
    if payload.get("id") is not None:
        return str(payload["id"])

    # Fallback: ibland ligger track id i "parts"
    parts = payload.get("parts")
    if isinstance(parts, list):
        for p in parts:
            if isinstance(p, dict) and p.get("object_track_id") is not None:
                return str(p["object_track_id"])

    return ""

def map_object_track_to_internal_event(
    *,
    payload: Dict[str, Any],
    source: SourceType,
    fallback_event_id: str,
) -> InternalEvent:
    """Mapper en validerad ObjectTrack payload till InternalEvent."""

    track_id = extract_track_id(payload)
    camera_id = str(payload.get("channel_id") or "")

    # Timestamp: använd start_time om den finns, annars end_time.
    ts = parse_axis_timestamp(payload.get("start_time") or payload.get("end_time"))

    # Snapshot-ref: behåll bara en liten referens, aldrig base64-datan.
    snapshot_ref = None
    image = payload.get("image")
    if isinstance(image, dict):
        img_id = image.get("id")
        if img_id is not None:
            snapshot_ref = f"axis-image:{img_id}"

    # Rensa bort tunga fält men behåll sök/analys-relevanta bitar.
    cleaned: Dict[str, Any] = {
        "channel_id": payload.get("channel_id"),
        "id": payload.get("id"),
        "start_time": payload.get("start_time"),
        "end_time": payload.get("end_time"),
        "duration": payload.get("duration"),
        "classes": payload.get("classes"),
        "path": payload.get("path"),
        "parts": payload.get("parts"),
        # Behåll image.id men inte image.data
        "image": {"id": image.get("id"), "type": image.get("type")} if isinstance(image, dict) else None,
    }

    return InternalEvent(
        event_id=fallback_event_id,
        track_id=track_id,
        camera_id=camera_id,
        timestamp=ts,
        snapshot_ref=snapshot_ref,
        source=source,
        payload=cleaned,
        event_type="object_track",
    )
def transform_axis_payload_to_internal_event(
    src: Dict[str, Any],
    source: SourceType,
    fallback_event_id: str,
) -> InternalEvent:
    # återanvänd er befintliga logik
    return map_object_track_to_internal_event(
        payload=src,
        source=source,
        fallback_event_id=fallback_event_id,
    )