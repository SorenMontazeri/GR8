#!/usr/bin/env python3

# Starta simulerad kamera på Windows från GR8/backend:
# .venv\Scripts\Activate.ps1
# python run_simulated_camera_windows.py `
#   --video recordings/1/D2026-03-31-T14-04-45.mp4 `
#   --events replay_out/live_events.jsonl `
#   --camera-id 1 `
#   --auto-filter-events `
#   --loop

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import imageio_ffmpeg


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


def _terminate_process(process: subprocess.Popen[str] | None, name: str) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        print(f"[windows-camera-runner] force-killing {name}")
        process.kill()
        process.wait(timeout=5)


def _wait_for_tcp(host: str, port: int, timeout_seconds: float = 15.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError(f"TCP service did not become available in time: {host}:{port}")


def _wait_for_rtsp(rtsp_url: str, timeout_seconds: float = 20.0) -> None:
    import cv2

    deadline = time.time() + timeout_seconds
    last_error = "RTSP stream did not become available in time."

    while time.time() < deadline:
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


def _candidate_bins(repo_root: Path, tools_dir: Path | None, *relative_paths: str) -> list[Path]:
    bases = [
        repo_root / "backend" / "tools",
        repo_root / "tools",
        repo_root / "tools" / "windows",
    ]
    if tools_dir is not None:
        bases.insert(0, tools_dir)
    candidates: list[Path] = []
    for base in bases:
        for rel in relative_paths:
            candidates.append(base / rel)
    return candidates


def _resolve_bin(explicit: str | None, repo_root: Path, tools_dir: Path | None, *relative_paths: str) -> str | None:
    if explicit:
        candidate = Path(explicit).expanduser()
        if candidate.exists():
            return str(candidate)
    for name in relative_paths:
        found = shutil.which(Path(name).name)
        if found:
            return found
    for candidate in _candidate_bins(repo_root, tools_dir, *relative_paths):
        if candidate.exists():
            return str(candidate)
    return None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Start the simulated camera stack on Windows. "
            "Looks for mediamtx.exe and uses mosquitto.exe if available, "
            "otherwise falls back to a local Python MQTT broker."
        )
    )
    parser.add_argument("--video", required=True, help="Path to scenario MP4 video.")
    parser.add_argument("--events", help="Path to scenario JSONL events or raw live MQTT JSONL.")
    parser.add_argument("--camera-id", default="1", help="Camera id for RTSP and MQTT topic.")
    parser.add_argument("--broker-host", default="127.0.0.1", help="MQTT broker host.")
    parser.add_argument("--broker-port", type=int, default=1883, help="MQTT broker port.")
    parser.add_argument("--rtsp-host", default="127.0.0.1", help="RTSP server host.")
    parser.add_argument("--rtsp-port", type=int, default=8554, help="RTSP server port.")
    parser.add_argument("--warmup-seconds", type=float, default=5.0, help="Simulator warmup before MQTT replay starts.")
    parser.add_argument("--loop", action="store_true", help="Loop simulator video and MQTT scenario forever.")
    parser.add_argument("--auto-filter-events", action="store_true", help="Auto-filter raw live event JSONL to the selected video.")
    parser.add_argument("--no-mqtt", action="store_true", help="Stream RTSP only and skip MQTT replay.")
    parser.add_argument("--skip-mediamtx", action="store_true", help="Do not start mediamtx automatically.")
    parser.add_argument("--skip-broker", action="store_true", help="Do not start any MQTT broker automatically.")
    parser.add_argument("--mediamtx-bin", help="Path to mediamtx.exe.")
    parser.add_argument("--mosquitto-bin", help="Path to mosquitto.exe.")
    parser.add_argument("--tools-dir", help="Optional directory that contains mediamtx.exe and mosquitto.exe.")
    parser.add_argument(
        "--use-python-broker",
        action="store_true",
        help="Force a local Python MQTT broker instead of mosquitto.exe.",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parent
    repo_root = backend_dir.parent
    python_executable = sys.executable
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    tools_dir = Path(args.tools_dir).expanduser() if args.tools_dir else None

    mediamtx_bin = _resolve_bin(
        args.mediamtx_bin,
        repo_root,
        tools_dir,
        "mediamtx.exe",
        "mediamtx/mediamtx.exe",
        "windows/mediamtx/mediamtx.exe",
    )
    mosquitto_bin = _resolve_bin(
        args.mosquitto_bin,
        repo_root,
        tools_dir,
        "mosquitto.exe",
        "mosquitto/mosquitto.exe",
        "windows/mosquitto/mosquitto.exe",
    )

    if not args.skip_mediamtx and mediamtx_bin is None:
        parser.error(
            "Could not find mediamtx.exe. Put it in PATH or pass --mediamtx-bin / --tools-dir."
        )
    if not args.no_mqtt and not args.events:
        parser.error("--events is required unless --no-mqtt is used.")
    if not args.skip_broker and not args.use_python_broker and mosquitto_bin is None:
        print("[windows-camera-runner] mosquitto.exe not found, falling back to Python broker")
        args.use_python_broker = True

    rtsp_url = f"rtsp://{args.rtsp_host}:{args.rtsp_port}/{args.camera_id}"
    mqtt_topic = f"camera/{args.camera_id}"

    mediamtx_process: subprocess.Popen[str] | None = None
    broker_process: subprocess.Popen[str] | None = None
    simulator_process: subprocess.Popen[str] | None = None

    try:
        if not args.skip_mediamtx:
            mediamtx_process = _start_process(
                [mediamtx_bin, "mediamtx.yml"],
                prefix="mediamtx",
                cwd=backend_dir,
            )
            time.sleep(1.0)

        if not args.no_mqtt and not args.skip_broker:
            if args.use_python_broker:
                broker_process = _start_process(
                    [
                        python_executable,
                        "-m",
                        "ingestion.simulator.local_broker",
                        "--host",
                        args.broker_host,
                        "--port",
                        str(args.broker_port),
                    ],
                    prefix="python-broker",
                    cwd=backend_dir,
                )
            else:
                broker_process = _start_process(
                    [mosquitto_bin, "-p", str(args.broker_port)],
                    prefix="mosquitto",
                    cwd=backend_dir,
                )
            _wait_for_tcp(args.broker_host, args.broker_port)

        simulator_cmd = [
            python_executable,
            "-m",
            "ingestion.simulator.simulated_camera",
            "--video",
            args.video,
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
                    args.events,
                    "--broker-host",
                    args.broker_host,
                    "--broker-port",
                    str(args.broker_port),
                ]
            )
            if args.auto_filter_events:
                simulator_cmd.append("--auto-filter-events")

        simulator_process = _start_process(simulator_cmd, prefix="simulator", cwd=backend_dir)

        _wait_for_rtsp(rtsp_url)
        print("[windows-camera-runner] simulated camera is live")
        print(f"[windows-camera-runner] RTSP read URL: {rtsp_url}")
        if not args.no_mqtt:
            broker_kind = "python broker" if args.use_python_broker else "mosquitto"
            print(f"[windows-camera-runner] MQTT broker: {args.broker_host}:{args.broker_port} ({broker_kind})")
            print(f"[windows-camera-runner] MQTT topic: {mqtt_topic}")
        print("[windows-camera-runner] start ingestion separately when you want")
        print("[windows-camera-runner] press Ctrl+C to stop camera stack")

        while True:
            time.sleep(60)
            if simulator_process.poll() is not None:
                raise RuntimeError("simulator process exited unexpectedly")

    except KeyboardInterrupt:
        print("[windows-camera-runner] stopping...")
        return 0
    finally:
        _terminate_process(simulator_process, "simulator")
        _terminate_process(broker_process, "broker")
        _terminate_process(mediamtx_process, "mediamtx")


if __name__ == "__main__":
    raise SystemExit(main())
