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

        def _save_analysis(*args, **kwargs):
            return None

        database_mod.save_analysis = _save_analysis
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

    def query_description_open(self, image_b64: str, image_mime: str = "image/jpeg") -> dict:
        self.calls.append({"image_b64": image_b64, "image_mime": image_mime})
        return {"description": "stub-description"}


class CameraOnMessageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.saved = []

        def _fake_save_analysis(*, created_at, description):
            self.saved.append({"created_at": created_at, "description": description})

        camera_module.save_analysis = _fake_save_analysis

    def _make_camera(self) -> Camera:
        cam = Camera.__new__(Camera)
        cam.camera_id = "cam-1"
        cam.frame_buffer = FrameRingBuffer(max_frames=10, max_bytes=10_000)
        from ingestion.buffers.mqtt_event_buffer import MqttEventRingBuffer
        cam.mqtt_buffer = MqttEventRingBuffer(max_events=100, max_bytes=100_000)
        cam.analysis_client = _SpyAnalysisClient()
        return cam

    def test_on_message_valid_json_uses_hot_buffer_and_saves_analysis(self) -> None:
        cam = self._make_camera()
        ts = datetime.now(timezone.utc)
        cam.frame_buffer.append(
            BufferedFrame(timestamp=ts, jpeg_bytes=b"fake-jpeg-bytes", width=10, height=10)
        )

        payload = {
            "id": "track-1",
            "channel_id": 1,
            "start_time": ts.isoformat().replace("+00:00", "Z"),
        }

        cam.on_message(None, None, _Msg(json.dumps(payload).encode("utf-8")))

        self.assertEqual(len(cam.analysis_client.calls), 1)
        self.assertEqual(cam.analysis_client.calls[0]["image_mime"], "image/jpeg")
        self.assertGreater(len(cam.analysis_client.calls[0]["image_b64"]), 0)
        self.assertEqual(len(self.saved), 1)
        self.assertEqual(self.saved[0]["description"], "stub-description")
        self.assertEqual(cam.mqtt_buffer.stats()["events"], 1)

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
