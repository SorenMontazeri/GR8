#!/usr/bin/env python3



from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path


def _stream_process_output(process: subprocess.Popen[str], prefix: str) -> threading.Thread:
    def _reader() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            print(f"[{prefix}] {line.rstrip()}")

    thread = threading.Thread(target=_reader, daemon=True)
    thread.start()
    return thread


def _start_process(
    cmd: list[str],
    prefix: str,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.Popen[str]:
    process = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env,
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
        print(f"[app-stack] force-killing {name}")
        process.kill()
        process.wait(timeout=5)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Start the app stack for E2E testing: ingestion + database API + frontend."
    )
    parser.add_argument("--camera-id", default="1", help="Camera id used by ingestion.")
    parser.add_argument("--rtsp-url", default="rtsp://127.0.0.1:8554/1", help="RTSP read URL for ingestion.")
    parser.add_argument("--broker-host", default="127.0.0.1", help="MQTT broker host.")
    parser.add_argument("--broker-port", type=int, default=1883, help="MQTT broker port.")
    parser.add_argument("--segment-seconds", type=int, default=10, help="Recording segment duration.")
    parser.add_argument("--stats-interval", type=float, default=10.0, help="How often ingestion stats are printed.")
    parser.add_argument("--api-key", help="API key for real analysis. Falls back to FACADE_API_KEY env var.")
    parser.add_argument("--model", default="prisma_gemini_pro", help="LLM model name.")
    parser.add_argument(
        "--endpoint",
        default="https://api.ai.auth.axis.cloud/v1/chat/completions",
        help="LLM endpoint.",
    )
    parser.add_argument("--stub-analysis", action="store_true", help="Use local stub analysis client.")
    parser.add_argument("--no-analysis", action="store_true", help="Disable analysis entirely.")
    parser.add_argument("--no-mqtt", action="store_true", help="Disable MQTT in ingestion.")
    parser.add_argument("--database-host", default="127.0.0.1", help="Database API host.")
    parser.add_argument("--database-port", type=int, default=8000, help="Database API port.")
    parser.add_argument("--frontend-host", default="127.0.0.1", help="Frontend dev server host.")
    parser.add_argument("--frontend-port", type=int, default=5173, help="Frontend dev server port.")
    parser.add_argument("--skip-database", action="store_true", help="Do not start database API automatically.")
    parser.add_argument("--skip-frontend", action="store_true", help="Do not start frontend automatically.")
    parser.add_argument("--skip-ingestion", action="store_true", help="Do not start ingestion automatically.")
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    backend_dir = repo_root / "backend"
    frontend_dir = repo_root / "frontend"
    python_executable = sys.executable
    npm_bin = shutil.which("npm")

    if not args.skip_frontend and npm_bin is None:
        parser.error("npm is not installed or not in PATH.")

    env = os.environ.copy()
    if args.api_key:
        env["FACADE_API_KEY"] = args.api_key

    database_process: subprocess.Popen[str] | None = None
    frontend_process: subprocess.Popen[str] | None = None
    ingestion_process: subprocess.Popen[str] | None = None

    try:
        if not args.skip_database:
            database_cmd = [
                python_executable,
                "-m",
                "uvicorn",
                "database:app",
                "--reload",
                "--app-dir",
                "database",
                "--host",
                args.database_host,
                "--port",
                str(args.database_port),
            ]
            database_process = _start_process(database_cmd, prefix="database", cwd=backend_dir, env=env)
            time.sleep(1.0)

        if not args.skip_frontend:
            frontend_cmd = [
                npm_bin,
                "run",
                "dev",
                "--",
                "--host",
                args.frontend_host,
                "--port",
                str(args.frontend_port),
            ]
            frontend_process = _start_process(frontend_cmd, prefix="frontend", cwd=frontend_dir, env=env)
            time.sleep(1.0)

        if not args.skip_ingestion:
            ingestion_cmd = [
                python_executable,
                "run_ingestion.py",
                "--camera-id",
                str(args.camera_id),
                "--rtsp-url",
                args.rtsp_url,
                "--broker-host",
                args.broker_host,
                "--broker-port",
                str(args.broker_port),
                "--segment-seconds",
                str(args.segment_seconds),
                "--stats-interval",
                str(args.stats_interval),
                "--model",
                args.model,
                "--endpoint",
                args.endpoint,
            ]
            if args.stub_analysis:
                ingestion_cmd.append("--stub-analysis")
            if args.no_analysis:
                ingestion_cmd.append("--no-analysis")
            if args.no_mqtt:
                ingestion_cmd.append("--no-mqtt")

            ingestion_process = _start_process(ingestion_cmd, prefix="ingestion", cwd=backend_dir, env=env)

        print("[app-stack] started")
        if not args.skip_ingestion:
            print(f"[app-stack] ingestion RTSP: {args.rtsp_url}")
            if not args.no_mqtt:
                print(f"[app-stack] ingestion MQTT: {args.broker_host}:{args.broker_port} topic=camera/{args.camera_id}")
        if not args.skip_database:
            print(f"[app-stack] database API: http://{args.database_host}:{args.database_port}")
        if not args.skip_frontend:
            print(f"[app-stack] frontend: http://localhost:{args.frontend_port}")
        print("[app-stack] start simulated camera separately with run_simulated_camera.py if needed")
        print("[app-stack] press Ctrl+C to stop")

        while True:
            time.sleep(60)
            if ingestion_process is not None and ingestion_process.poll() is not None:
                raise RuntimeError("ingestion process exited unexpectedly")
            if database_process is not None and database_process.poll() is not None:
                raise RuntimeError("database process exited unexpectedly")
            if frontend_process is not None and frontend_process.poll() is not None:
                raise RuntimeError("frontend process exited unexpectedly")

    except KeyboardInterrupt:
        print("[app-stack] stopping...")
        return 0
    finally:
        _terminate_process(ingestion_process, "ingestion")
        _terminate_process(frontend_process, "frontend")
        _terminate_process(database_process, "database")


if __name__ == "__main__":
    raise SystemExit(main())
