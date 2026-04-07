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
import shutil
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
    parser.add_argument("--video", required=True, help="Path to scenario MP4 video.")
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
                    "--auto-filter-events" if args.auto_filter_events else "",
                    "--broker-host",
                    args.broker_host,
                    "--broker-port",
                    str(args.broker_port),
                ]
            )
            simulator_cmd = [part for part in simulator_cmd if part]

        simulator_process = _start_process(simulator_cmd, prefix="simulator", cwd=backend_dir)

        _wait_for_rtsp(rtsp_url)
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
