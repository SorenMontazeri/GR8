#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import imageio_ffmpeg
import paho.mqtt.client as mqtt


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _default_session_dir(camera_id: str) -> Path:
    root = Path(__file__).resolve().parent / "database" / "recordings" / str(camera_id)
    session_name = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    return root / session_name


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture a live RTSP+MQTT session into a replayable session directory."
    )
    parser.add_argument("--camera-id", default="1", help="Camera id. Used for session path and MQTT topic.")
    parser.add_argument("--rtsp-url", required=True, help="Live camera RTSP URL to record.")
    parser.add_argument("--broker-host", default="127.0.0.1", help="MQTT broker host.")
    parser.add_argument("--broker-port", type=int, default=1883, help="MQTT broker port.")
    parser.add_argument(
        "--topic",
        help="MQTT topic to subscribe to. Defaults to camera/<camera_id>.",
    )
    parser.add_argument(
        "--session-dir",
        help="Output session directory. Defaults to backend/database/recordings/<camera_id>/session_<timestamp>.",
    )
    parser.add_argument(
        "--duration-seconds",
        type=float,
        help="Optional capture duration. If omitted, capture runs until Ctrl+C.",
    )
    parser.add_argument(
        "--ffmpeg-path",
        default=imageio_ffmpeg.get_ffmpeg_exe(),
        help="Path to ffmpeg executable.",
    )
    return parser


def _start_ffmpeg_recording(ffmpeg_path: str, rtsp_url: str, output_file: Path) -> subprocess.Popen[bytes]:
    cmd = [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "warning",
        "-rtsp_transport",
        "tcp",
        "-i",
        rtsp_url,
        "-an",
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        str(output_file),
    ]
    return subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _terminate_process(process: subprocess.Popen[Any] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    topic = args.topic or f"camera/{args.camera_id}"
    session_dir = Path(args.session_dir) if args.session_dir else _default_session_dir(args.camera_id)
    session_dir.mkdir(parents=True, exist_ok=False)
    video_file = session_dir / "capture.mp4"
    events_file = session_dir / "events.jsonl"
    manifest_file = session_dir / "manifest.json"

    capture_start_wallclock = _utc_now()
    capture_start_monotonic = time.monotonic()

    manifest = {
        "camera_id": str(args.camera_id),
        "created_at": _isoformat_z(capture_start_wallclock),
        "capture_start_wallclock": _isoformat_z(capture_start_wallclock),
        "video": video_file.name,
        "events": events_file.name,
        "topic": topic,
        "rtsp_url": args.rtsp_url,
    }
    manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    events_handle = events_file.open("w", encoding="utf-8")
    ffmpeg_process = _start_ffmpeg_recording(args.ffmpeg_path, args.rtsp_url, video_file)

    stop_requested = False

    def _request_stop(signum=None, frame=None) -> None:
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)

    mqtt_client = mqtt.Client()

    def _on_message(client, userdata, msg) -> None:
        received_at = _utc_now()
        try:
            raw_payload = json.loads(msg.payload.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            return
        if not isinstance(raw_payload, dict):
            return
        offset_ms = int(round((time.monotonic() - capture_start_monotonic) * 1000.0))
        record = {
            "offset_ms": max(offset_ms, 0),
            "received_at": _isoformat_z(received_at),
            "raw": raw_payload,
        }
        events_handle.write(json.dumps(record) + "\n")
        events_handle.flush()

    mqtt_client.on_message = _on_message
    mqtt_client.connect(args.broker_host, args.broker_port, 60)
    mqtt_client.subscribe(topic)
    mqtt_client.loop_start()

    print(f"[live-capture] session dir: {session_dir}")
    print(f"[live-capture] recording video to: {video_file}")
    print(f"[live-capture] writing events to: {events_file}")
    print(f"[live-capture] MQTT topic: {topic}")
    if args.duration_seconds is not None:
        print(f"[live-capture] duration: {args.duration_seconds}s")
    else:
        print("[live-capture] press Ctrl+C to stop")

    try:
        if args.duration_seconds is not None:
            deadline = time.monotonic() + args.duration_seconds
            while not stop_requested and time.monotonic() < deadline:
                if ffmpeg_process.poll() is not None:
                    raise RuntimeError("ffmpeg recording process exited unexpectedly")
                time.sleep(0.2)
        else:
            while not stop_requested:
                if ffmpeg_process.poll() is not None:
                    raise RuntimeError("ffmpeg recording process exited unexpectedly")
                time.sleep(0.2)
    finally:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        events_handle.close()
        _terminate_process(ffmpeg_process)

    print("[live-capture] session completed")
    print(f"[live-capture] replay with: python run_simulated_camera.py --session {session_dir} --camera-id {args.camera_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
