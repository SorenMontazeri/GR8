#!/usr/bin/env python3

# Starta simulerad kamera från GR8/backend:
# source .venv/bin/activate
# python run_simulated_camera.py \
#   --video recordings/1/D2026-03-31-T14-04-45.mp4 \
#   --events replay_out/live_events.jsonl \
#   --camera-id 1 \
#   --auto-filter-events \
#   --loop

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import imageio_ffmpeg
from ingestion.simulator.scenario_loader import _extract_original_timestamp, _load_jsonl


_SEGMENT_NAME_RE = re.compile(r"^segment-(\d+)(?:_.*)?\.mp4$")
_RECORDING_TZ = ZoneInfo("Europe/Stockholm")


def _stream_process_output(process: subprocess.Popen[str], prefix: str) -> threading.Thread:
    def _reader() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            print(f"[{prefix}] {line.rstrip()}")

    thread = threading.Thread(target=_reader, daemon=True)
    thread.start()
    return thread


def _start_process(cmd: list[str], prefix: str, cwd: Path) -> subprocess.Popen[str]:
    process = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )
    _stream_process_output(process, prefix)
    return process


def _wait_for_rtsp(
    rtsp_url: str,
    timeout_seconds: float = 20.0,
    watched_process: subprocess.Popen[str] | None = None,
) -> None:
    import cv2

    deadline = time.time() + timeout_seconds
    last_error = "RTSP stream did not become available in time."

    while time.time() < deadline:
        if watched_process is not None and watched_process.poll() is not None:
            raise RuntimeError("simulator process exited before RTSP stream became available")
        capture = cv2.VideoCapture(rtsp_url)
        if capture.isOpened():
            ok, frame = capture.read()
            capture.release()
            if ok and frame is not None:
                return
            last_error = "RTSP opened but no frame could be read yet."
        else:
            capture.release()
            last_error = "RTSP could not be opened yet."
        time.sleep(0.5)

    raise RuntimeError(last_error)


def _terminate_process(process: subprocess.Popen[str] | None, name: str) -> None:
    if process is None:
        return
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        print(f"[camera-runner] force-killing {name}")
        process.kill()
        process.wait(timeout=5)


def _parse_segment_range(value: str) -> tuple[int, int]:
    text = value.strip()
    match = re.fullmatch(r"(\d+)\s*:\s*(\d+)", text)
    if match is None:
        raise ValueError("segment range must use the format START:END, for example 263:277")

    start = int(match.group(1))
    end = int(match.group(2))
    if start > end:
        raise ValueError("segment range start must be <= end")
    return start, end


def _segment_index_from_name(file_name: str) -> int | None:
    match = _SEGMENT_NAME_RE.match(Path(file_name).name)
    if match is None:
        return None
    return int(match.group(1))


def _resolve_segment_range_assets(
    *,
    backend_dir: Path,
    camera_id: str,
    range_start: int,
    range_end: int,
    ffmpeg_path: str,
) -> tuple[Path, Path]:
    index_path = backend_dir / "indexes" / f"index-{camera_id}.csv"
    recordings_dir = backend_dir / "recordings" / str(camera_id)
    if not index_path.exists():
        raise FileNotFoundError(f"Index file not found: {index_path}")

    rows_by_index: dict[int, dict[str, str]] = {}
    with index_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            idx = _segment_index_from_name(row.get("file_name", ""))
            if idx is None:
                continue
            rows_by_index[idx] = row

    selected_rows: list[dict[str, str]] = []
    missing: list[int] = []
    for idx in range(range_start, range_end + 1):
        row = rows_by_index.get(idx)
        if row is None:
            missing.append(idx)
            continue
        selected_rows.append(row)

    if missing:
        raise FileNotFoundError(
            "Missing segment index row(s) for: " + ", ".join(str(idx) for idx in missing)
        )

    first_start = datetime.fromisoformat(selected_rows[0]["segment_start_camera_time"])
    last_end = datetime.fromisoformat(selected_rows[-1]["segment_end_camera_time"])
    local_start = first_start.astimezone(_RECORDING_TZ)
    output_name = local_start.strftime("D%Y-%m-%d-T%H-%M-%S.mp4")

    generated_dir = backend_dir / "replay_out" / "generated" / f"camera_{camera_id}_{range_start:05d}_{range_end:05d}"
    generated_dir.mkdir(parents=True, exist_ok=True)

    concat_list = generated_dir / "segments.txt"
    output_video = generated_dir / output_name
    output_events = generated_dir / "filtered_events.jsonl"

    concat_lines: list[str] = []
    for row in selected_rows:
        file_name = row["file_name"]
        segment_path = Path(file_name)
        if not segment_path.is_absolute():
            segment_path = recordings_dir / file_name
        if not segment_path.exists():
            raise FileNotFoundError(f"Segment file not found: {segment_path}")
        concat_lines.append(f"file '{segment_path.resolve().as_posix()}'")

    concat_list.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")

    subprocess.run(
        [
            ffmpeg_path,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-c",
            "copy",
            str(output_video),
        ],
        check=True,
        cwd=str(backend_dir),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    return output_video, output_events


def _filter_events_for_time_window(
    *,
    source_events: Path,
    output_events: Path,
    window_start: datetime,
    window_end: datetime,
) -> int:
    raw_events = _load_jsonl(source_events)
    selected: list[dict[str, Any]] = []
    for payload in raw_events:
        original_ts = _extract_original_timestamp(payload)
        if original_ts is None:
            continue
        if window_start <= original_ts < window_end:
            selected.append(payload)

    if not selected:
        raise ValueError(
            "No MQTT events matched the selected segment time window. "
            f"window_start={window_start.isoformat()} window_end={window_end.isoformat()}"
        )

    output_events.write_text(
        "".join(json.dumps(event) + "\n" for event in selected),
        encoding="utf-8",
    )
    return len(selected)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Start a simulated camera source stack (MediaMTX + Mosquitto + simulator) without ingestion."
    )
    parser.add_argument("--video", help="Path to scenario MP4 video.")
    parser.add_argument(
        "--segment-range",
        help="Inclusive segment range to concatenate from recordings/index, for example 263:277.",
    )
    parser.add_argument("--events", help="Path to scenario JSONL events.")
    parser.add_argument("--camera-id", default="1", help="Camera id for RTSP and MQTT topic.")
    parser.add_argument("--broker-host", default="127.0.0.1", help="MQTT broker host.")
    parser.add_argument("--broker-port", type=int, default=1883, help="MQTT broker port.")
    parser.add_argument("--rtsp-host", default="127.0.0.1", help="RTSP server host.")
    parser.add_argument("--rtsp-port", type=int, default=8554, help="RTSP server port.")
    parser.add_argument("--warmup-seconds", type=float, default=5.0, help="Simulator warmup before MQTT replay starts.")
    parser.add_argument("--loop", action="store_true", help="Loop simulator video and MQTT scenario forever.")
    parser.add_argument(
        "--auto-filter-events",
        action="store_true",
        help=(
            "Treat --events as a raw live JSONL file and let the simulator select only the MQTT "
            "events that belong to the chosen video's time window."
        ),
    )
    parser.add_argument("--no-mqtt", action="store_true", help="Stream RTSP only and skip MQTT replay.")
    parser.add_argument("--skip-mediamtx", action="store_true", help="Do not start mediamtx automatically.")
    parser.add_argument("--skip-mosquitto", action="store_true", help="Do not start mosquitto automatically.")
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parent
    python_executable = sys.executable
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    mediamtx_bin = shutil.which("mediamtx")
    mosquitto_bin = shutil.which("mosquitto")

    if not args.skip_mediamtx and mediamtx_bin is None:
        parser.error("mediamtx is not installed or not in PATH.")
    if not args.skip_mosquitto and mosquitto_bin is None:
        parser.error("mosquitto is not installed or not in PATH.")
    if not args.no_mqtt and not args.events:
        parser.error("--events is required unless --no-mqtt is used.")
    if bool(args.video) == bool(args.segment_range):
        parser.error("Provide exactly one of --video or --segment-range.")

    rtsp_url = f"rtsp://{args.rtsp_host}:{args.rtsp_port}/{args.camera_id}"
    mqtt_topic = f"camera/{args.camera_id}"

    video_path = args.video
    events_path = args.events
    auto_filter_events = args.auto_filter_events
    if args.segment_range:
        try:
            range_start, range_end = _parse_segment_range(args.segment_range)
        except ValueError as exc:
            parser.error(str(exc))
        try:
            resolved_video, resolved_events = _resolve_segment_range_assets(
                backend_dir=backend_dir,
                camera_id=str(args.camera_id),
                range_start=range_start,
                range_end=range_end,
                ffmpeg_path=ffmpeg_path,
            )
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            parser.error(str(exc))
        index_path = backend_dir / "indexes" / f"index-{args.camera_id}.csv"
        rows_by_index: dict[int, dict[str, str]] = {}
        with index_path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                idx = _segment_index_from_name(row.get("file_name", ""))
                if idx is not None:
                    rows_by_index[idx] = row
        first_row = rows_by_index[range_start]
        last_row = rows_by_index[range_end]
        window_start = datetime.fromisoformat(first_row["segment_start_camera_time"])
        window_end = datetime.fromisoformat(last_row["segment_end_camera_time"])
        try:
            selected_events = _filter_events_for_time_window(
                source_events=Path(args.events),
                output_events=resolved_events,
                window_start=window_start,
                window_end=window_end,
            )
        except ValueError as exc:
            parser.error(str(exc))
        video_path = str(resolved_video)
        events_path = str(resolved_events)
        auto_filter_events = False
        print(f"[camera-runner] built segment-range video: {resolved_video}")
        print(
            "[camera-runner] filtered MQTT events:",
            f"window={window_start.isoformat()}->{window_end.isoformat()}",
            f"selected={selected_events}",
            f"events_file={resolved_events}",
        )

    mediamtx_process: subprocess.Popen[str] | None = None
    mosquitto_process: subprocess.Popen[str] | None = None
    simulator_process: subprocess.Popen[str] | None = None

    try:
        if not args.skip_mediamtx:
            mediamtx_process = _start_process(
                [mediamtx_bin, "mediamtx.yml"],
                prefix="mediamtx",
                cwd=backend_dir,
            )
            time.sleep(1.0)

        if not args.skip_mosquitto:
            mosquitto_process = _start_process(
                [mosquitto_bin, "-p", str(args.broker_port)],
                prefix="mosquitto",
                cwd=backend_dir,
            )
            time.sleep(1.0)

        simulator_cmd = [
            python_executable,
            "-m",
            "ingestion.simulator.simulated_camera",
            "--video",
            video_path,
            "--camera-id",
            str(args.camera_id),
            "--rtsp-publish-url",
            rtsp_url,
            "--warmup-seconds",
            str(args.warmup_seconds),
            "--ffmpeg-path",
            ffmpeg_path,
        ]
        if args.loop:
            simulator_cmd.append("--loop")
        if args.no_mqtt:
            simulator_cmd.append("--no-mqtt")
        else:
            simulator_cmd.extend(
                [
                    "--events",
                    events_path,
                    "--auto-filter-events" if auto_filter_events else "",
                    "--broker-host",
                    args.broker_host,
                    "--broker-port",
                    str(args.broker_port),
                ]
            )
            simulator_cmd = [part for part in simulator_cmd if part]

        simulator_process = _start_process(simulator_cmd, prefix="simulator", cwd=backend_dir)

        _wait_for_rtsp(rtsp_url, watched_process=simulator_process)
        print("[camera-runner] simulated camera is live")
        print(f"[camera-runner] RTSP read URL: {rtsp_url}")
        if not args.no_mqtt:
            print(f"[camera-runner] MQTT broker: {args.broker_host}:{args.broker_port}")
            print(f"[camera-runner] MQTT topic: {mqtt_topic}")
        print("[camera-runner] start ingestion separately when you want")
        print("[camera-runner] press Ctrl+C to stop camera stack")

        while True:
            time.sleep(60)
            if simulator_process.poll() is not None:
                raise RuntimeError("simulator process exited unexpectedly")

    except KeyboardInterrupt:
        print("[camera-runner] stopping...")
        return 0
    finally:
        _terminate_process(simulator_process, "simulator")
        _terminate_process(mosquitto_process, "mosquitto")
        _terminate_process(mediamtx_process, "mediamtx")


if __name__ == "__main__":
    raise SystemExit(main())
