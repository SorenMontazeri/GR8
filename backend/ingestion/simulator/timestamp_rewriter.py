from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Dict


def _to_axis_timestamp(value: datetime) -> str:
    utc_value = value.astimezone(timezone.utc)
    return utc_value.isoformat().replace("+00:00", "Z")


def rewrite_payload_timestamps(
    payload: Dict[str, Any],
    *,
    original_event_timestamp: datetime,
    simulation_start_wallclock_utc: datetime,
    offset_ms: int,
) -> Dict[str, Any]:
    rewritten = deepcopy(payload)
    new_event_time = simulation_start_wallclock_utc + timedelta(milliseconds=offset_ms)
    shift = new_event_time - original_event_timestamp

    if isinstance(rewritten.get("start_time"), str):
        rewritten["start_time"] = _to_axis_timestamp(new_event_time)

    if isinstance(rewritten.get("end_time"), str):
        original_end = payload.get("end_time")
        try:
            parsed_end = datetime.fromisoformat(str(original_end).replace("Z", "+00:00"))
            rewritten["end_time"] = _to_axis_timestamp(parsed_end + shift)
        except ValueError:
            rewritten["end_time"] = _to_axis_timestamp(new_event_time)

    image = rewritten.get("image")
    if isinstance(image, dict) and isinstance(image.get("timestamp"), str):
        original_image_ts = payload.get("image", {}).get("timestamp")
        try:
            parsed_image = datetime.fromisoformat(str(original_image_ts).replace("Z", "+00:00"))
            image["timestamp"] = _to_axis_timestamp(parsed_image + shift)
        except ValueError:
            image["timestamp"] = _to_axis_timestamp(new_event_time)

    path_entries = rewritten.get("path")
    original_path_entries = payload.get("path")
    if isinstance(path_entries, list) and isinstance(original_path_entries, list):
        for index, entry in enumerate(path_entries):
            if not isinstance(entry, dict):
                continue
            original_entry = original_path_entries[index] if index < len(original_path_entries) else None
            original_ts = original_entry.get("timestamp") if isinstance(original_entry, dict) else None
            if not isinstance(entry.get("timestamp"), str):
                continue
            try:
                parsed_path_ts = datetime.fromisoformat(str(original_ts).replace("Z", "+00:00"))
                entry["timestamp"] = _to_axis_timestamp(parsed_path_ts + shift)
            except ValueError:
                entry["timestamp"] = _to_axis_timestamp(new_event_time)

    return rewritten
