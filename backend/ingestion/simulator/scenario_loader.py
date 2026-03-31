from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

try:
    import cv2
except ModuleNotFoundError:  # pragma: no cover - optional for thin envs
    cv2 = None

try:
    import imageio_ffmpeg
except ModuleNotFoundError:  # pragma: no cover - optional for thin envs
    imageio_ffmpeg = None


_VIDEO_NAME_PATTERN = re.compile(r"^D(\d{4}-\d{2}-\d{2}-T\d{2}-\d{2}-\d{2})\.mp4$")
_RECORDING_TZ = ZoneInfo("Europe/Stockholm")


def _parse_axis_timestamp_strict(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def _extract_original_timestamp(payload: Dict[str, Any]) -> datetime | None:
    start_time = _parse_axis_timestamp_strict(payload.get("start_time"))
    if start_time is not None:
        return start_time

    image = payload.get("image")
    if isinstance(image, dict):
        image_ts = _parse_axis_timestamp_strict(image.get("timestamp"))
        if image_ts is not None:
            return image_ts

    return None


def _unwrap_scenario_payload(parsed: Dict[str, Any]) -> Dict[str, Any]:
    raw = parsed.get("raw")
    if isinstance(raw, dict):
        return raw
    return parsed


def _infer_video_start_from_name(video: Path) -> datetime | None:
    match = _VIDEO_NAME_PATTERN.match(video.name)
    if match is None:
        return None
    try:
        naive = datetime.strptime(match.group(1), "%Y-%m-%d-T%H-%M-%S")
        return naive.replace(tzinfo=_RECORDING_TZ)
    except ValueError:
        return None


def _probe_video_duration_ms(video: Path) -> int | None:
    duration_ms = _probe_video_duration_ms_cv2(video)
    if duration_ms is not None:
        return duration_ms
    return _probe_video_duration_ms_ffmpeg(video)


def _probe_video_duration_ms_cv2(video: Path) -> int | None:
    if cv2 is None:
        return None
    capture = cv2.VideoCapture(str(video))
    try:
        if not capture.isOpened():
            return None
        fps = capture.get(cv2.CAP_PROP_FPS)
        frame_count = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        if fps <= 0 or frame_count <= 0:
            return None
        return int(round((frame_count / fps) * 1000.0))
    finally:
        capture.release()


def _probe_video_duration_ms_ffmpeg(video: Path) -> int | None:
    if imageio_ffmpeg is None:
        return None
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    proc = subprocess.run(
        [ffmpeg_exe, "-i", str(video)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    output = proc.stderr or ""
    match = re.search(r"Duration:\s*(\d{2}):(\d{2}):(\d{2}\.\d+)", output)
    if match is None:
        return None
    hours = int(match.group(1))
    minutes = int(match.group(2))
    seconds = float(match.group(3))
    total_ms = int(round(((hours * 3600) + (minutes * 60) + seconds) * 1000.0))
    return total_ms if total_ms > 0 else None


@dataclass(frozen=True)
class VideoTimeWindow:
    start: datetime
    end: datetime
    duration_ms: int


def _infer_video_time_window(video: Path, target_tz) -> VideoTimeWindow | None:
    video_start = _infer_video_start_from_name(video)
    video_duration_ms = _probe_video_duration_ms(video)
    if video_start is None or video_duration_ms is None:
        return None

    localized_start = video_start.astimezone(target_tz)
    return VideoTimeWindow(
        start=localized_start,
        end=localized_start + timedelta(milliseconds=video_duration_ms),
        duration_ms=video_duration_ms,
    )


def _filter_events_to_video_window(
    video: Path,
    timed_events: List[tuple[datetime, Dict[str, Any]]],
    *,
    require_match: bool = False,
) -> tuple[List[tuple[datetime, Dict[str, Any]]], VideoTimeWindow | None, int]:
    if not timed_events:
        return timed_events, None, 0

    video_window = _infer_video_time_window(video, timed_events[0][0].tzinfo)
    if video_window is None:
        if require_match:
            raise ValueError(
                "Could not infer video time window from filename and duration. "
                "Expected a file named like DYYYY-MM-DD-THH-MM-SS.mp4 and a readable MP4 duration."
            )
        return timed_events, None, 0

    filtered = [
        (ts, payload)
        for ts, payload in timed_events
        if video_window.start <= ts < video_window.end
    ]
    if not filtered:
        if require_match:
            raise ValueError(
                "No MQTT events matched the inferred video time window. "
                f"window_start={video_window.start.isoformat()} "
                f"window_end={video_window.end.isoformat()} "
                f"video={video}"
            )
        return timed_events, video_window, 0
    return filtered, video_window, len(filtered)


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL at line {line_no}: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError(f"Scenario event at line {line_no} is not a JSON object.")
        unwrapped = _unwrap_scenario_payload(parsed)
        if not isinstance(unwrapped, dict):
            raise ValueError(f"Scenario event at line {line_no} did not unwrap to a JSON object.")
        rows.append(unwrapped)
    return rows


@dataclass(frozen=True)
class ScenarioEvent:
    offset_ms: int
    original_timestamp: datetime
    payload: Dict[str, Any]


@dataclass(frozen=True)
class Scenario:
    video_path: Path
    events_path: Path
    events: List[ScenarioEvent]
    total_events_loaded: int
    filtered_events_loaded: int
    auto_filtered: bool
    video_window: VideoTimeWindow | None

    @property
    def duration_ms(self) -> int:
        if not self.events:
            return 0
        return self.events[-1].offset_ms


def load_scenario(
    video_path: str | Path,
    events_path: str | Path,
    *,
    auto_filter_events: bool = False,
) -> Scenario:
    """Load simulator input as a replayable scenario.

    When auto_filter_events is enabled, the events file may be a larger raw
    live JSONL capture. In that mode the loader infers the video's time window
    from the recording filename and video duration, then keeps only the MQTT
    events that fall within that window.
    """
    video = Path(video_path)
    events_file = Path(events_path)

    if not video.exists():
        raise FileNotFoundError(f"Scenario video not found: {video}")
    if not events_file.exists():
        raise FileNotFoundError(f"Scenario events file not found: {events_file}")

    raw_events = _load_jsonl(events_file)
    if not raw_events:
        raise ValueError("Scenario events file is empty.")

    timed_events: List[tuple[datetime, Dict[str, Any]]] = []
    for index, payload in enumerate(raw_events, start=1):
        original_ts = _extract_original_timestamp(payload)
        if original_ts is None:
            raise ValueError(
                f"Scenario event {index} has no usable timestamp. "
                "Expected start_time or image.timestamp."
            )
        timed_events.append((original_ts, payload))

    timed_events.sort(key=lambda item: item[0])
    total_events_loaded = len(timed_events)
    timed_events, video_window, filtered_events_loaded = _filter_events_to_video_window(
        video,
        timed_events,
        require_match=auto_filter_events,
    )
    base_ts = timed_events[0][0]

    events: List[ScenarioEvent] = []
    for original_ts, payload in timed_events:
        delta_ms = int(round((original_ts - base_ts).total_seconds() * 1000.0))
        if delta_ms < 0:
            raise ValueError("Scenario event offset became negative after sorting.")
        events.append(
            ScenarioEvent(
                offset_ms=delta_ms,
                original_timestamp=original_ts,
                payload=payload,
            )
        )

    return Scenario(
        video_path=video,
        events_path=events_file,
        events=events,
        total_events_loaded=total_events_loaded,
        filtered_events_loaded=filtered_events_loaded,
        auto_filtered=auto_filter_events,
        video_window=video_window,
    )
