#!/usr/bin/env python3

# Starta simulerad kamera från GR8/backend:
# source venv/bin/activate
# python run_simulated_camera.py \
#   --session database/recordings/1/session_20260420_143456 \
#   --camera-id 1 \
#   --loop
#
# Eller i äldre filbaserat läge:
# python run_simulated_camera.py \
#   --video database/recordings/1/D2026-03-31-T14-04-45.mp4 \
#   --events replay_out/live_events.jsonl \
#   --camera-id 1 \
#   --auto-filter-events \
#   --loop

from __future__ import annotations

import argparse
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import imageio_ffmpeg

from ingestion.simulator.scenario_loader import load_session_manifest


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


def _wait_for_tcp_listener(host: str, port: int, timeout_seconds: float = 10.0) -> None:
    deadline = time.time() + timeout_seconds
    last_error = f"{host}:{port} did not open in time."

    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return
        except OSError as exc:
            last_error = str(exc)
            time.sleep(0.2)

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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Start a simulated camera source stack (MediaMTX + Mosquitto + simulator) without ingestion."
    )
    parser.add_argument("--session", help="Path to a recorded session directory with manifest.json, events.jsonl and video.")
    parser.add_argument(
        "--latest-session",
        action="store_true",
        help="Use the newest recorded session under backend/database/recordings/<camera_id>/.",
    )
    parser.add_argument("--video", help="Path to scenario MP4 video.")
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


def _find_latest_session(backend_dir: Path, camera_id: str) -> Path:
    sessions_root = backend_dir / "database" / "recordings" / str(camera_id)
    if not sessions_root.exists():
        raise FileNotFoundError(f"No recordings directory found for camera_id={camera_id}: {sessions_root}")

    session_dirs = [
        path
        for path in sessions_root.iterdir()
        if path.is_dir() and path.name.startswith("session_") and (path / "manifest.json").exists()
    ]
    if not session_dirs:
        raise FileNotFoundError(f"No session directories found for camera_id={camera_id} in {sessions_root}")

    return max(session_dirs, key=lambda path: path.name)


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
    selected_session = args.session
    if args.latest_session:
        if args.session:
            parser.error("Use either --session or --latest-session, not both.")
        selected_session = str(_find_latest_session(backend_dir, str(args.camera_id)))

    if not selected_session and not args.video:
        parser.error("Either --session, --latest-session, or --video is required.")
    if selected_session and args.video:
        parser.error("Use a session mode or --video, not both.")
    if not args.no_mqtt and not selected_session and not args.events:
        parser.error("--events is required unless --no-mqtt is used.")

    rtsp_url = f"rtsp://{args.rtsp_host}:{args.rtsp_port}/{args.camera_id}"
    mqtt_topic = f"camera/{args.camera_id}"

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
            _wait_for_tcp_listener(args.rtsp_host, args.rtsp_port)

        if not args.skip_mosquitto:
            mosquitto_process = _start_process(
                [mosquitto_bin, "-p", str(args.broker_port)],
                prefix="mosquitto",
                cwd=backend_dir,
            )
            _wait_for_tcp_listener(args.broker_host, args.broker_port)

        if selected_session:
            manifest = load_session_manifest(selected_session)
            camera_id = manifest.camera_id
            if str(args.camera_id) != camera_id:
                parser.error(
                    f"--camera-id {args.camera_id} does not match session camera_id {camera_id}."
                )

        simulator_cmd = [
            python_executable,
            "-m",
            "ingestion.simulator.simulated_camera",
            "--camera-id",
            str(args.camera_id),
            "--rtsp-publish-url",
            rtsp_url,
            "--warmup-seconds",
            str(args.warmup_seconds),
            "--ffmpeg-path",
            ffmpeg_path,
        ]
        if selected_session:
            simulator_cmd.extend(["--session", selected_session])
        else:
            simulator_cmd.extend(["--video", args.video])
        if args.loop:
            simulator_cmd.append("--loop")
        if args.no_mqtt:
            simulator_cmd.append("--no-mqtt")
        else:
            if not selected_session:
                simulator_cmd.extend(["--events", args.events])
                if args.auto_filter_events:
                    simulator_cmd.append("--auto-filter-events")
            simulator_cmd.extend(
                [
                    "--broker-host",
                    args.broker_host,
                    "--broker-port",
                    str(args.broker_port),
                ]
            )

        simulator_process = _start_process(simulator_cmd, prefix="simulator", cwd=backend_dir)

        _wait_for_rtsp(rtsp_url)
        print("[camera-runner] simulated camera is live")
        if selected_session:
            print(f"[camera-runner] session: {selected_session}")
        print(f"[camera-runner] RTSP read URL: {rtsp_url}")
        if not args.no_mqtt:
            print(f"[camera-runner] MQTT broker: {args.broker_host}:{args.broker_port}")
            print(f"[camera-runner] MQTT topic: {mqtt_topic}")
        print("[camera-runner] start ingestion separately when you want")
        print("[camera-runner] press Ctrl+C to stop camera stack")

        while True:
            time.sleep(60)
            if simulator_process.poll() is not None:
                raise RuntimeError(
                    f"simulator process exited unexpectedly with code {simulator_process.returncode}"
                )

    except KeyboardInterrupt:
        print("[camera-runner] stopping...")
        return 0
    finally:
        _terminate_process(simulator_process, "simulator")
        _terminate_process(mosquitto_process, "mosquitto")
        _terminate_process(mediamtx_process, "mediamtx")


if __name__ == "__main__":
    raise SystemExit(main())
