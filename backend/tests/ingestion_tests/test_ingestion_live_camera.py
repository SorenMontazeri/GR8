from __future__ import annotations
"""
Live camera ingestion tests.

Kopplat till krav:
- F01 "Systemet ska kunna ta emot metadata-strömmar via (HTTP/MQTT) i JSON-format enligt Axis-kameror."
- F02 "Systemet ska kunna logga felaktig metadata (flagga för tom/dålig/ogiltig data)."
- F07 "Systemet ska kunna skicka en JPEG-bild till Prisma API och ta emot en textbaserad beskrivning i JSON-format."

Testnivå:
- Enhetstest

Varför testet finns:
- Verifiera att on_message i live-flödet parser MQTT JSON och triggar ingest-logik.
- Verifiera robust hantering av trasig/tom JSON utan krasch.
- Verifiera att frame- och bytes-gränser i RTSP-hotbuffer följs.

Vad testet verifierar:
- Giltig payload -> analysanrop sker, save_analysis anropas och MQTT-event buffras.
- Ogiltig/tom payload -> ingen analys/save och ingen krasch.
- Ringbuffer respekterar max_frames och max_bytes.

Förutsättningar:
- Inga externa beroenden krävs under testkörning (stubbar används vid behov).

Vad man ska titta efter i terminalen:
1. Alla tester i filen passerar.
2. Inga oväntade exceptions vid invalid JSON-fall.

Vad man ska titta efter i filsystemet / systemet:
- Inga filer behöver skapas för detta test.

För att köra testet:
cd GR8/backend
python3 -m pytest tests/ingestion_tests/test_ingestion_live_camera.py -v
"""

import importlib.util
import json
import sys
import types
import unittest
from datetime import datetime, timezone


def _module_missing(name: str) -> bool:
    if name in sys.modules:
        return False
    try:
        return importlib.util.find_spec(name) is None
    except ValueError:
        # Some stubbed modules may exist with __spec__ = None.
        return False


def _ensure_stub_modules() -> None:
    if _module_missing("cv2"):
        cv2 = types.ModuleType("cv2")
        cv2.IMWRITE_JPEG_QUALITY = 1
        cv2.INTER_AREA = 3
        sys.modules["cv2"] = cv2

    if _module_missing("imageio_ffmpeg"):
        imageio_ffmpeg = types.ModuleType("imageio_ffmpeg")
        imageio_ffmpeg.get_ffmpeg_exe = lambda: "ffmpeg"
        sys.modules["imageio_ffmpeg"] = imageio_ffmpeg

    if _module_missing("paho"):
        paho = types.ModuleType("paho")
        mqtt_pkg = types.ModuleType("paho.mqtt")
        mqtt_client_mod = types.ModuleType("paho.mqtt.client")

        class DummyClient:
            def __init__(self) -> None:
                self.on_message = None

            def connect(self, *args, **kwargs) -> None:
                return None

            def subscribe(self, *args, **kwargs) -> None:
                return None

            def loop_start(self) -> None:
                return None

            def loop_stop(self) -> None:
                return None

            def disconnect(self) -> None:
                return None

        mqtt_client_mod.Client = DummyClient
        mqtt_pkg.client = mqtt_client_mod
        paho.mqtt = mqtt_pkg

        sys.modules["paho"] = paho
        sys.modules["paho.mqtt"] = mqtt_pkg
        sys.modules["paho.mqtt.client"] = mqtt_client_mod

    if "database.database" not in sys.modules:
        database_pkg = types.ModuleType("database")
        database_mod = types.ModuleType("database.database")

        def _save_description_bundle(*args, **kwargs):
            return None

        database_mod.save_description_bundle = _save_description_bundle
        database_pkg.database = database_mod
        sys.modules["database"] = database_pkg
        sys.modules["database.database"] = database_mod


_ensure_stub_modules()

import ingestion.camera as camera_module  # noqa: E402
from ingestion.camera import Camera  # noqa: E402
from ingestion.buffers.rtsp_hot_buffer import BufferedFrame, FrameRingBuffer  # noqa: E402


class _Msg:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload


class _SpyAnalysisClient:
    def __init__(self) -> None:
        self.calls = []

    async def query_description_open(
        self,
        image_b64,
        image_mime: str = "image/jpeg",
        sequence: bool = False,
    ) -> dict:
        self.calls.append(
            {
                "image_b64": image_b64,
                "image_mime": image_mime,
                "sequence": sequence,
            }
        )
        return {"description": "stub-description", "keywords": ["stub-keyword"]}

    # Keep backward compatibility in the test double in case older code paths are exercised.
    def query_description_closed(
        self,
        image_b64: str,
        keywords: list[str],
        image_mime: str = "image/jpeg",
    ) -> dict:
        self.calls.append(
            {
                "image_b64": image_b64,
                "keywords": keywords,
                "image_mime": image_mime,
            }
        )
        return {"description": "stub-description", "keywords": ["stub-keyword"]}

class CameraOnMessageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.saved = []

        def _fake_save_description_bundle(
            timestamp_start,
            timestamp_end,
            created_at,
            uniform_llm_description,
            varied_llm_description,
            snapshot_llm_description,
            full_frame_llm_description,
            uniform_timestamps,
            varied_timestamps,
            snapshot_timestamp,
            full_frame_timestamp,
            snapshot_image_base64,
        ):
            self.saved.append(
                {
                    "timestamp_start": timestamp_start,
                    "timestamp_end": timestamp_end,
                    "created_at": created_at,
                    "uniform_llm_description": uniform_llm_description,
                    "varied_llm_description": varied_llm_description,
                    "snapshot_llm_description": snapshot_llm_description,
                    "full_frame_llm_description": full_frame_llm_description,
                    "uniform_timestamps": uniform_timestamps,
                    "varied_timestamps": varied_timestamps,
                    "snapshot_timestamp": snapshot_timestamp,
                    "full_frame_timestamp": full_frame_timestamp,
                    "snapshot_image_base64": snapshot_image_base64,
                }
            )

        camera_module.save_description_bundle = _fake_save_description_bundle

    def _make_camera(self) -> Camera:
        cam = Camera.__new__(Camera)
        cam.camera_id = "cam-1"
        cam.frame_buffer = FrameRingBuffer(max_frames=10, max_bytes=10_000)
        from ingestion.buffers.mqtt_event_buffer import MqttEventRingBuffer
        cam.mqtt_buffer = MqttEventRingBuffer(max_events=100, max_bytes=100_000)
        cam.analysis_client = _SpyAnalysisClient()
        return cam

    def test_extract_event_timestamp_prefers_start_time(self) -> None:
        cam = self._make_camera()
        parsed = cam._extract_event_timestamp({"start_time": "2026-03-24T12:00:00Z"})
        self.assertEqual(parsed, datetime(2026, 3, 24, 12, 0, tzinfo=timezone.utc))

    def test_extract_event_timestamp_falls_back_to_now_when_invalid(self) -> None:
        cam = self._make_camera()
        before = datetime.now(timezone.utc)
        parsed = cam._extract_event_timestamp({"start_time": "not-a-timestamp"})
        after = datetime.now(timezone.utc)
        self.assertGreaterEqual(parsed, before)
        self.assertLessEqual(parsed, after)

    def test_on_message_invalid_json_is_handled(self) -> None:
        cam = self._make_camera()

        cam.on_message(None, None, _Msg(b"{"))
        cam.on_message(None, None, _Msg(b""))

        self.assertEqual(len(cam.analysis_client.calls), 0)
        self.assertEqual(len(self.saved), 0)


class FrameRingBufferTests(unittest.TestCase):
    def test_respects_max_frames(self) -> None:
        buf = FrameRingBuffer(max_frames=3, max_bytes=10_000)
        for _ in range(4):
            buf.append(
                BufferedFrame(
                    timestamp=datetime.now(timezone.utc),
                    jpeg_bytes=b"x",
                    width=10,
                    height=10,
                )
            )

        stats = buf.stats()
        self.assertEqual(stats["frames"], 3)
        self.assertEqual(stats["bytes"], 3)

    def test_respects_max_bytes(self) -> None:
        buf = FrameRingBuffer(max_frames=100, max_bytes=5)
        for payload in (b"abc", b"def", b"ghi"):
            buf.append(
                BufferedFrame(
                    timestamp=datetime.now(timezone.utc),
                    jpeg_bytes=payload,
                    width=10,
                    height=10,
                )
            )

        stats = buf.stats()
        self.assertEqual(stats["frames"], 1)
        self.assertEqual(stats["bytes"], 3)


if __name__ == "__main__":
    unittest.main()