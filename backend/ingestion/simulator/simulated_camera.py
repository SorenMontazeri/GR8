from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

try:
    import imageio_ffmpeg
except ModuleNotFoundError:  # pragma: no cover - optional in thin test envs
    imageio_ffmpeg = None

from ingestion.simulator.mqtt_replayer import MqttReplayer
from ingestion.simulator.rtsp_streamer import RtspStreamer
from ingestion.simulator.scenario_loader import (
    Scenario,
    load_scenario,
    load_scenario_from_session,
    load_session_manifest,
)


@dataclass(frozen=True)
class SimulationResult:
    published_events: int
    scenario_duration_ms: int


class SimulatedCamera:
    def __init__(
        self,
        *,
        video_path: str | Path,
        scenario: Scenario | None,
        camera_id: str,
        broker_host: str | None,
        broker_port: int | None,
        rtsp_publish_url: str,
        ffmpeg_path: str,
        warmup_seconds: float = 2.0,
        loop_scenario: bool = False,
    ) -> None:
        self.video_path = str(video_path)
        self.scenario = scenario
        self.camera_id = str(camera_id)
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.rtsp_publish_url = rtsp_publish_url
        self.ffmpeg_path = ffmpeg_path
        self.warmup_seconds = warmup_seconds
        self.loop_scenario = loop_scenario
        self.rtsp_streamer = RtspStreamer(
            ffmpeg_path=self.ffmpeg_path,
            video_path=self.video_path,
            publish_url=self.rtsp_publish_url,
            loop_forever=(self.scenario is not None and self.loop_scenario),
        )
        self.mqtt_replayer = None
        if self.scenario is not None:
            if self.broker_host is None or self.broker_port is None:
                raise ValueError("broker_host and broker_port are required when MQTT replay is enabled.")
            self.mqtt_replayer = MqttReplayer(
                scenario=self.scenario,
                camera_id=self.camera_id,
                broker_host=self.broker_host,
                broker_port=self.broker_port,
            )

    def run(self) -> SimulationResult:
        self.rtsp_streamer.start()
        try:
            if self.warmup_seconds > 0:
                time.sleep(self.warmup_seconds)
            if self.mqtt_replayer is None:
                self.rtsp_streamer.wait()
                return SimulationResult(
                    published_events=0,
                    scenario_duration_ms=0,
                )
            published = 0
            while True:
                simulation_start = datetime.now(timezone.utc)
                published += self.mqtt_replayer.run(simulation_start)
                if not self.loop_scenario:
                    break
                if self.mqtt_replayer.stopped():
                    break
            return SimulationResult(
                published_events=published,
                scenario_duration_ms=self.scenario.duration_ms if self.scenario is not None else 0,
            )
        finally:
            self.rtsp_streamer.stop()

    def stop(self) -> None:
        if self.mqtt_replayer is not None:
            self.mqtt_replayer.stop()
        self.rtsp_streamer.stop()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a simulated live camera scenario.")
    parser.add_argument("--session", help="Path to a recorded session directory with manifest.json, events.jsonl and video.")
    parser.add_argument("--video", help="Path to scenario MP4 video.")
    parser.add_argument("--events", help="Path to scenario JSONL events or raw live MQTT JSONL.")
    parser.add_argument("--camera-id", required=True, help="Camera id used for MQTT topic.")
    parser.add_argument("--broker-host", help="MQTT broker host.")
    parser.add_argument("--broker-port", type=int, default=1883, help="MQTT broker port.")
    parser.add_argument("--rtsp-publish-url", required=True, help="RTSP publish URL on the RTSP server.")
    parser.add_argument("--warmup-seconds", type=float, default=2.0, help="Delay before MQTT replay starts.")
    parser.add_argument(
        "--auto-filter-events",
        action="store_true",
        help=(
            "Treat --events as a larger raw JSONL stream and automatically keep only events "
            "that fall within the recorded video's inferred time window."
        ),
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Loop both RTSP video and MQTT scenario forever until interrupted.",
    )
    parser.add_argument(
        "--no-mqtt",
        action="store_true",
        help="Stream only video over RTSP and skip MQTT replay entirely.",
    )
    parser.add_argument(
        "--ffmpeg-path",
        default=imageio_ffmpeg.get_ffmpeg_exe() if imageio_ffmpeg is not None else "ffmpeg",
        help="Path to ffmpeg executable.",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    if args.session:
        manifest = load_session_manifest(args.session)
        video_path = str(manifest.video_path)
        if args.no_mqtt:
            scenario = None
        else:
            if not args.broker_host:
                parser.error("--broker-host is required unless --no-mqtt is used.")
            _, scenario = load_scenario_from_session(args.session)
    else:
        if not args.video:
            parser.error("--video is required unless --session is used.")
        video_path = args.video
        if args.no_mqtt:
            scenario = None
        else:
            if not args.events:
                parser.error("--events is required unless --no-mqtt is used.")
            if not args.broker_host:
                parser.error("--broker-host is required unless --no-mqtt is used.")
            scenario = load_scenario(args.video, args.events, auto_filter_events=args.auto_filter_events)
    if scenario is not None:
        if scenario.video_window is not None:
            print(
                "Scenario prepared:",
                f"video_window={scenario.video_window.start.isoformat()}->{scenario.video_window.end.isoformat()}",
                f"events_loaded={scenario.total_events_loaded}",
                f"events_selected={len(scenario.events)}",
                f"auto_filtered={scenario.auto_filtered}",
            )
        else:
            print(
                "Scenario prepared:",
                f"events_loaded={scenario.total_events_loaded}",
                f"events_selected={len(scenario.events)}",
                f"auto_filtered={scenario.auto_filtered}",
            )

    simulator = SimulatedCamera(
        video_path=video_path,
        scenario=scenario,
        camera_id=args.camera_id,
        broker_host=args.broker_host,
        broker_port=args.broker_port,
        rtsp_publish_url=args.rtsp_publish_url,
        ffmpeg_path=args.ffmpeg_path,
        warmup_seconds=args.warmup_seconds,
        loop_scenario=args.loop,
    )
    try:
        result = simulator.run()
        print(
            "Simulation completed:",
            f"events={result.published_events}",
            f"duration_ms={result.scenario_duration_ms}",
            f"camera_id={args.camera_id}",
        )
    except KeyboardInterrupt:
        simulator.stop()
        print("Simulation interrupted.")


if __name__ == "__main__":
    main()
