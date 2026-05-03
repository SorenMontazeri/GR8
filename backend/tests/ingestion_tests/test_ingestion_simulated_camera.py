from __future__ import annotations

"""
Simulated live camera support tests.

Kopplat till krav:
- F01 "Systemet ska kunna ta emot metadata-strömmar via (HTTP/MQTT) i JSON-format enligt Axis-kameror."
- F03 "Systemet ska kunna hantera inspelad data på samma sätt som live-data."
- F04 "Systemet ska synkronisera inkommande metadata med tillhörande bildrutor baserat på tidstämplar."

Testnivå:
- Enhetstest

Varför testet finns:
- Verifiera att simulatorns scenarioformat kan läsas och schemaläggas i realtid.
- Verifiera att timestamps skrivs om till nutid konsekvent före MQTT-publicering.
- Verifiera att MQTT-replayer publicerar i offset-ordning på rätt topic.

Vad testet verifierar:
- Scenario-loader räknar fram rätt offset_ms från JSONL.
- Timestamp-rewriter uppdaterar start_time, end_time, image.timestamp och path[*].timestamp.
- MQTT-replayer publicerar omskriven payload i rätt ordning och med nutidsbaserad tidslinje.

Förutsättningar:
- Inga externa tjänster krävs. MQTT-klient stubbas i testerna.

Vad man ska titta efter i terminalen:
1. Alla tester i filen passerar.

Vad man ska titta efter i filsystemet / systemet:
- Tillfälliga testfiler skapas och städas bort automatiskt.

För att köra testet:
Inga externa tjänster behöver startas först. Detta är ett unit-test för simulatorns interna logik.
Glöm inte starta venv också: source .venv/bin/activate
cd GR8/backend
python3 -m pytest tests/ingestion_tests/test_ingestion_simulated_camera.py -v
"""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import run_simulated_camera as camera_runner
from ingestion.simulator.mqtt_replayer import MqttReplayer
from ingestion.simulator.scenario_loader import load_scenario
from ingestion.simulator.simulated_camera import SimulatedCamera
from ingestion.simulator.timestamp_rewriter import rewrite_payload_timestamps


class _FakeMqttClient:
    def __init__(self) -> None:
        self.connected = False
        self.published: list[tuple[str, dict]] = []

    def connect(self, host: str, port: int, keepalive: int) -> None:
        self.connected = True

    def loop_start(self) -> None:
        return None

    def loop_stop(self) -> None:
        return None

    def disconnect(self) -> None:
        self.connected = False

    def publish(self, topic: str, payload: str) -> object:
        self.published.append((topic, json.loads(payload)))
        return object()


class _FakeRtspStreamer:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.waited = False

    def start(self):
        self.started = True
        return object()

    def wait(self) -> int:
        self.waited = True
        return 0

    def stop(self) -> None:
        self.stopped = True


class _FakeLoopingReplayer:
    def __init__(self) -> None:
        self.calls = 0
        self._stopped = False

    def run(self, simulation_start) -> int:
        self.calls += 1
        if self.calls >= 2:
            self._stopped = True
        return 3

    def stop(self) -> None:
        self._stopped = True

    def stopped(self) -> bool:
        return self._stopped


class ScenarioLoaderTests(unittest.TestCase):
    def test_segment_range_parser_accepts_expected_format(self) -> None:
        self.assertEqual(camera_runner._parse_segment_range("263:277"), (263, 277))
        self.assertEqual(camera_runner._parse_segment_range(" 7 : 9 "), (7, 9))

    def test_segment_range_parser_rejects_invalid_format(self) -> None:
        with self.assertRaises(ValueError):
            camera_runner._parse_segment_range("277-263")
        with self.assertRaises(ValueError):
            camera_runner._parse_segment_range("300:200")

    def test_resolve_segment_range_assets_creates_concat_video_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend_dir = Path(temp_dir)
            recordings_dir = backend_dir / "recordings" / "1"
            indexes_dir = backend_dir / "indexes"
            recordings_dir.mkdir(parents=True)
            indexes_dir.mkdir(parents=True)

            (recordings_dir / "segment-00263_2026-05-03T21-31-44Z.mp4").write_bytes(b"a")
            (recordings_dir / "segment-00264_2026-05-03T21-31-54Z.mp4").write_bytes(b"b")
            (indexes_dir / "index-1.csv").write_text(
                "file_name,segment_start_camera_time,segment_end_camera_time\n"
                "segment-00263_2026-05-03T21-31-44Z.mp4,2026-05-03T21:31:44+00:00,2026-05-03T21:31:53+00:00\n"
                "segment-00264_2026-05-03T21-31-54Z.mp4,2026-05-03T21:31:54+00:00,2026-05-03T21:32:03+00:00\n",
                encoding="utf-8",
            )

            def _fake_run(cmd, check, cwd, stdin, stdout, stderr, text):
                output_path = Path(cmd[-1])
                output_path.write_bytes(b"fake-joined-video")
                return object()

            with patch("run_simulated_camera.subprocess.run", side_effect=_fake_run):
                output_video, output_events = camera_runner._resolve_segment_range_assets(
                    backend_dir=backend_dir,
                    camera_id="1",
                    range_start=263,
                    range_end=264,
                    ffmpeg_path="ffmpeg",
                )

            self.assertTrue(output_video.exists())
            self.assertEqual(output_events.name, "filtered_events.jsonl")
            self.assertEqual(output_video.parent.name, "camera_1_00263_00264")
            self.assertTrue(output_video.name.startswith("D2026-05-03-T23-31-44"))
            concat_list = output_video.parent / "segments.txt"
            self.assertTrue(concat_list.exists())
            concat_text = concat_list.read_text(encoding="utf-8")
            self.assertIn("segment-00263_2026-05-03T21-31-44Z.mp4", concat_text)
            self.assertIn("segment-00264_2026-05-03T21-31-54Z.mp4", concat_text)

    def test_filter_events_for_time_window_writes_selected_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_events = temp_path / "live_events.jsonl"
            output_events = temp_path / "filtered_events.jsonl"
            source_events.write_text(
                "\n".join(
                    [
                        json.dumps({"id": "before", "start_time": "2026-05-03T20:01:37Z"}),
                        json.dumps({"id": "inside-1", "start_time": "2026-05-03T20:01:38Z"}),
                        json.dumps({"id": "inside-2", "start_time": "2026-05-03T20:03:00Z"}),
                        json.dumps({"id": "after", "start_time": "2026-05-03T20:03:46Z"}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            count = camera_runner._filter_events_for_time_window(
                source_events=source_events,
                output_events=output_events,
                window_start=datetime(2026, 5, 3, 20, 1, 38, tzinfo=timezone.utc),
                window_end=datetime(2026, 5, 3, 20, 3, 45, tzinfo=timezone.utc),
            )

            self.assertEqual(count, 2)
            lines = [json.loads(line) for line in output_events.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([row["id"] for row in lines], ["inside-1", "inside-2"])

    def _write_scenario_files(self, events: list[dict]) -> tuple[str, str]:
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".mp4", delete=False) as video_fp:
            video_path = video_fp.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as events_fp:
            for event in events:
                events_fp.write(json.dumps(event) + "\n")
            events_path = events_fp.name
        self.addCleanup(lambda: Path(video_path).unlink(missing_ok=True))
        self.addCleanup(lambda: Path(events_path).unlink(missing_ok=True))
        return video_path, events_path

    def test_load_scenario_computes_offsets_from_start_time(self) -> None:
        video_path, events_path = self._write_scenario_files(
            [
                {"id": "b", "start_time": "2026-03-24T12:00:00.250Z"},
                {"id": "a", "start_time": "2026-03-24T12:00:00.000Z"},
                {"id": "c", "start_time": "2026-03-24T12:00:00.900Z"},
            ]
        )

        scenario = load_scenario(video_path, events_path)

        self.assertEqual([event.payload["id"] for event in scenario.events], ["a", "b", "c"])
        self.assertEqual([event.offset_ms for event in scenario.events], [0, 250, 900])

    def test_load_scenario_falls_back_to_image_timestamp(self) -> None:
        video_path, events_path = self._write_scenario_files(
            [
                {"id": "img-only", "image": {"timestamp": "2026-03-24T12:00:01.000Z"}},
            ]
        )

        scenario = load_scenario(video_path, events_path)

        self.assertEqual(len(scenario.events), 1)
        self.assertEqual(scenario.events[0].offset_ms, 0)

    def test_load_scenario_accepts_wrapped_raw_event_store_format(self) -> None:
        video_path, events_path = self._write_scenario_files(
            [
                {
                    "received_at": "2026-03-24T11:59:59Z",
                    "source": "live",
                    "raw": {
                        "id": "wrapped-1",
                        "start_time": "2026-03-24T12:00:00.000Z",
                    },
                }
            ]
        )

        scenario = load_scenario(video_path, events_path)

        self.assertEqual(len(scenario.events), 1)
        self.assertEqual(scenario.events[0].payload["id"], "wrapped-1")
        self.assertEqual(scenario.events[0].offset_ms, 0)

    def test_load_scenario_can_auto_filter_raw_live_events_to_video_window(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            video_path = temp_path / "D2026-03-31-T14-04-45.mp4"
            video_path.write_bytes(b"fake-mp4")
            events_path = temp_path / "live_events.jsonl"
            events_path.write_text(
                "\n".join(
                    [
                        json.dumps({"id": "before", "start_time": "2026-03-31T12:04:44.900Z"}),
                        json.dumps({"id": "inside-1", "start_time": "2026-03-31T12:04:45.000Z"}),
                        json.dumps({"id": "inside-2", "start_time": "2026-03-31T12:04:46.200Z"}),
                        json.dumps({"id": "after", "start_time": "2026-03-31T12:04:50.500Z"}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            with patch("ingestion.simulator.scenario_loader._probe_video_duration_ms", return_value=5000):
                scenario = load_scenario(video_path, events_path, auto_filter_events=True)

        self.assertEqual([event.payload["id"] for event in scenario.events], ["inside-1", "inside-2"])
        self.assertEqual(scenario.total_events_loaded, 4)
        self.assertEqual(scenario.filtered_events_loaded, 2)
        self.assertTrue(scenario.auto_filtered)
        self.assertIsNotNone(scenario.video_window)


class TimestampRewriterTests(unittest.TestCase):
    def test_rewrite_payload_timestamps_updates_all_supported_fields(self) -> None:
        payload = {
            "start_time": "2026-03-24T12:00:00.000Z",
            "end_time": "2026-03-24T12:00:01.500Z",
            "image": {"timestamp": "2026-03-24T12:00:00.200Z"},
            "path": [
                {"timestamp": "2026-03-24T12:00:00.300Z"},
                {"timestamp": "2026-03-24T12:00:00.600Z"},
            ],
        }
        simulation_start = datetime(2026, 3, 24, 15, 0, 0, tzinfo=timezone.utc)

        rewritten = rewrite_payload_timestamps(
            payload,
            original_event_timestamp=datetime(2026, 3, 24, 12, 0, 0, tzinfo=timezone.utc),
            simulation_start_wallclock_utc=simulation_start,
            offset_ms=500,
        )

        self.assertEqual(rewritten["start_time"], "2026-03-24T15:00:00.500000Z")
        self.assertEqual(rewritten["end_time"], "2026-03-24T15:00:02Z")
        self.assertEqual(rewritten["image"]["timestamp"], "2026-03-24T15:00:00.700000Z")
        self.assertEqual(rewritten["path"][0]["timestamp"], "2026-03-24T15:00:00.800000Z")
        self.assertEqual(rewritten["path"][1]["timestamp"], "2026-03-24T15:00:01.100000Z")


class MqttReplayerTests(unittest.TestCase):
    def _write_scenario_files(self, events: list[dict]) -> tuple[str, str]:
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".mp4", delete=False) as video_fp:
            video_path = video_fp.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as events_fp:
            for event in events:
                events_fp.write(json.dumps(event) + "\n")
            events_path = events_fp.name
        self.addCleanup(lambda: Path(video_path).unlink(missing_ok=True))
        self.addCleanup(lambda: Path(events_path).unlink(missing_ok=True))
        return video_path, events_path

    def test_mqtt_replayer_publishes_rewritten_payloads_in_order(self) -> None:
        video_path, events_path = self._write_scenario_files(
            [
                {"id": "a", "start_time": "2026-03-24T12:00:00.000Z"},
                {"id": "b", "start_time": "2026-03-24T12:00:00.150Z"},
            ]
        )
        scenario = load_scenario(video_path, events_path)
        fake_client = _FakeMqttClient()
        monotonic_values = iter([0.0, 0.0, 0.1, 0.2])

        def _fake_monotonic() -> float:
            return next(monotonic_values)

        slept: list[float] = []

        replayer = MqttReplayer(
            scenario=scenario,
            camera_id="cam-7",
            broker_host="127.0.0.1",
            broker_port=1883,
            client=fake_client,
            sleep_fn=slept.append,
            monotonic_fn=_fake_monotonic,
        )

        published = replayer.run(datetime(2026, 3, 24, 15, 0, 0, tzinfo=timezone.utc))

        self.assertEqual(published, 2)
        self.assertEqual([topic for topic, _ in fake_client.published], ["camera/cam-7", "camera/cam-7"])
        self.assertEqual([payload["id"] for _, payload in fake_client.published], ["a", "b"])
        self.assertEqual(
            [payload["start_time"] for _, payload in fake_client.published],
            ["2026-03-24T15:00:00Z", "2026-03-24T15:00:00.150000Z"],
        )
        self.assertTrue(any(delay > 0 for delay in slept))


class SimulatedCameraTests(unittest.TestCase):
    def test_run_without_mqtt_waits_for_rtsp_only(self) -> None:
        simulator = SimulatedCamera(
            video_path="dummy.mp4",
            scenario=None,
            camera_id="sim-rtsp-only",
            broker_host=None,
            broker_port=None,
            rtsp_publish_url="rtsp://127.0.0.1:8554/sim-rtsp-only",
            ffmpeg_path="ffmpeg",
            warmup_seconds=0,
        )
        fake_streamer = _FakeRtspStreamer()
        simulator.rtsp_streamer = fake_streamer

        result = simulator.run()

        self.assertEqual(result.published_events, 0)
        self.assertEqual(result.scenario_duration_ms, 0)
        self.assertTrue(fake_streamer.started)
        self.assertTrue(fake_streamer.waited)
        self.assertTrue(fake_streamer.stopped)

    def test_run_with_loop_replays_multiple_iterations_until_stopped(self) -> None:
        scenario = type("ScenarioStub", (), {"duration_ms": 2200, "events": []})()
        fake_streamer = _FakeRtspStreamer()
        fake_replayer = _FakeLoopingReplayer()

        with patch("ingestion.simulator.simulated_camera.MqttReplayer", return_value=fake_replayer):
            simulator = SimulatedCamera(
                video_path="dummy.mp4",
                scenario=scenario,
                camera_id="sim-loop",
                broker_host="127.0.0.1",
                broker_port=1883,
                rtsp_publish_url="rtsp://127.0.0.1:8554/sim-loop",
                ffmpeg_path="ffmpeg",
                warmup_seconds=0,
                loop_scenario=True,
            )
        simulator.rtsp_streamer = fake_streamer

        result = simulator.run()

        self.assertEqual(result.published_events, 6)
        self.assertEqual(result.scenario_duration_ms, 2200)
        self.assertEqual(fake_replayer.calls, 2)
        self.assertTrue(fake_streamer.started)
        self.assertTrue(fake_streamer.stopped)


if __name__ == "__main__":
    unittest.main()
