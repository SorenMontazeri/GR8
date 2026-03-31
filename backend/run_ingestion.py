#!/usr/bin/env python3

#skript som startar ingestion:
#cd GR8/backend 
# source .venv/bin/activate
#export FACADE_API_KEY='din_nyckel'
#
#python run_ingestion.py \
#  --camera-id 1 \
#  --rtsp-url rtsp://127.0.0.1:8554/1 \
#  --broker-host 127.0.0.1 \
#  --broker-port 1883


from __future__ import annotations

import argparse
import os
import time

import imageio_ffmpeg

from ingestion.camera import Camera


class StubAnalysisClient:
    def query_description_closed(self, frame_b64, labels, image_mime="image/jpeg"):
        return {"keywords": ["simulated", "frame-matched"]}


class NoMqttCamera(Camera):
    def init_mqtt(self, broker_host: str, broker_port: int) -> None:
        return None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Start ingestion against a live or simulated camera source.")
    parser.add_argument("--camera-id", default="1", help="Camera id used for MQTT topic and recordings path.")
    parser.add_argument("--rtsp-url", required=True, help="RTSP read URL.")
    parser.add_argument("--broker-host", default="127.0.0.1", help="MQTT broker host.")
    parser.add_argument("--broker-port", type=int, default=1883, help="MQTT broker port.")
    parser.add_argument("--segment-seconds", type=int, default=5, help="Recording segment duration.")
    parser.add_argument("--stats-interval", type=float, default=10.0, help="How often stats are printed.")
    parser.add_argument("--api-key", help="API key for real analysis. Falls back to FACADE_API_KEY env var.")
    parser.add_argument("--model", default="prisma_gemini_pro", help="LLM model name.")
    parser.add_argument(
        "--endpoint",
        default="https://api.ai.auth.axis.cloud/v1/chat/completions",
        help="LLM endpoint.",
    )
    parser.add_argument("--stub-analysis", action="store_true", help="Use local stub analysis client.")
    parser.add_argument("--no-analysis", action="store_true", help="Disable analysis entirely.")
    parser.add_argument("--no-mqtt", action="store_true", help="Disable MQTT and only run RTSP + recording + hotbuffer.")
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    analysis_client = None
    if args.no_analysis:
        analysis_client = None
    elif args.stub_analysis:
        analysis_client = StubAnalysisClient()
    else:
        api_key = args.api_key or os.environ.get("FACADE_API_KEY")
        if api_key:
            from analysis.sync_prisma import LLMClientSync

            analysis_client = LLMClientSync(args.endpoint, api_key, args.model)
        else:
            print("[ingestion-runner] no API key found, falling back to StubAnalysisClient")
            analysis_client = StubAnalysisClient()

    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    camera_class = NoMqttCamera if args.no_mqtt else Camera

    camera = camera_class(
        camera_id=str(args.camera_id),
        rtsp_url=args.rtsp_url,
        ffmpeg=ffmpeg_path,
        broker_host=args.broker_host,
        broker_port=args.broker_port,
        analysis_client=analysis_client,
        segment_seconds=args.segment_seconds,
    )

    print(f"[ingestion-runner] started for camera_id={args.camera_id}")
    print(f"[ingestion-runner] RTSP={args.rtsp_url}")
    if not args.no_mqtt:
        print(f"[ingestion-runner] MQTT={args.broker_host}:{args.broker_port} topic=camera/{args.camera_id}")
    if args.no_analysis:
        print("[ingestion-runner] analysis disabled")
    elif args.stub_analysis:
        print("[ingestion-runner] using StubAnalysisClient")
    else:
        print("[ingestion-runner] using analysis client")
    print("[ingestion-runner] press Ctrl+C to stop")

    try:
        while True:
            time.sleep(args.stats_interval)
            print("[ingestion-runner] Hot buffer stats:", camera.hot_buffer_stats())
            print("[ingestion-runner] MQTT buffer stats:", camera.mqtt_buffer_stats())
    except KeyboardInterrupt:
        print("[ingestion-runner] stopping...")
        return 0
    finally:
        camera.stop_recording()


if __name__ == "__main__":
    raise SystemExit(main())
