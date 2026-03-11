from __future__ import annotations

"""
MQTT + RTSP context matching tests.

Kopplat till krav:
- F04 "Systemet ska synkronisera inkommande metadata med tillhörande bildrutor baserat på tidstämplar."
- F08 "Logik för att hämta högupplösta bildrutor från videoströmmen som matchar tidpunkten för objektets snapshot."

Testnivå:
- Enhetstest

Varför testet finns:
- Verifiera timestamp-matchning i MQTT-hotbuffer.
- Verifiera att Camera.get_context_at returnerar samlad kontext (frame + event) när data finns inom tolerans.

Vad testet verifierar:
- search_event hittar närmaste MQTT-event inom tolerans och missar utanför tolerans.
- get_context_at kan returnera både frame och MQTT-event vid match.
- get_context_at returnerar frame utan MQTT-match när event ligger för långt bort i tid.

Förutsättningar:
- Inga externa beroenden krävs under testkörning (stubbar används vid behov).

Vad man ska titta efter i terminalen:
1. Alla tester i filen passerar.

Vad man ska titta efter i filsystemet / systemet:
- Inga filer behöver skapas för detta test.

För att köra testet:
cd GR8/backend
python3 -m pytest tests/ingestion_tests/test_ingestion_mqtt_context_matching.py -v
"""

import importlib.util
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone

from ingestion.buffers.mqtt_event_buffer import BufferedMqttEvent, MqttEventRingBuffer
from ingestion.buffers.rtsp_hot_buffer import BufferedFrame, FrameRingBuffer


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

        mqtt_client_mod.Client = DummyClient
        mqtt_pkg.client = mqtt_client_mod
        paho.mqtt = mqtt_pkg
        sys.modules["paho"] = paho
        sys.modules["paho.mqtt"] = mqtt_pkg
        sys.modules["paho.mqtt.client"] = mqtt_client_mod

    if "database.database" not in sys.modules:
        database_pkg = types.ModuleType("database")
        database_mod = types.ModuleType("database.database")
        database_mod.save_analysis = lambda *args, **kwargs: None
        database_pkg.database = database_mod
        sys.modules["database"] = database_pkg
        sys.modules["database.database"] = database_mod


_ensure_stub_modules()

from ingestion.camera import Camera


class MqttEventRingBufferTests(unittest.TestCase):
    def test_search_event_returns_nearest_within_tolerance(self) -> None:
        buf = MqttEventRingBuffer(max_events=10, max_bytes=10000)
        t0 = datetime.now(timezone.utc)
        e1 = BufferedMqttEvent(timestamp=t0, payload={"id": "a"})
        e2 = BufferedMqttEvent(timestamp=t0 + timedelta(milliseconds=200), payload={"id": "b"})
        buf.append(e1)
        buf.append(e2)

        hit = buf.search_event(t0 + timedelta(milliseconds=180), tolerance_ms=80)
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.payload["id"], "b")

        miss = buf.search_event(t0 + timedelta(seconds=5), tolerance_ms=100)
        self.assertIsNone(miss)


class CameraContextMatchingTests(unittest.TestCase):
    def _make_camera(self) -> Camera:
        cam = Camera.__new__(Camera)
        cam.camera_id = "cam-ctx"
        cam.frame_buffer = FrameRingBuffer(max_frames=50, max_bytes=100000)
        cam.mqtt_buffer = MqttEventRingBuffer(max_events=50, max_bytes=100000)
        return cam

    def test_get_context_at_returns_frame_and_mqtt_event(self) -> None:
        cam = self._make_camera()
        target = datetime.now(timezone.utc)
        cam.frame_buffer.append(
            BufferedFrame(timestamp=target, jpeg_bytes=b"frame-bytes", width=10, height=10)
        )
        cam.mqtt_buffer.append(
            BufferedMqttEvent(timestamp=target + timedelta(milliseconds=120), payload={"id": "evt-1"})
        )

        ctx = cam.get_context_at(target, tolerance_ms=200)
        self.assertTrue(ctx["frame_found"])
        self.assertTrue(ctx["mqtt_found"])
        self.assertEqual(ctx["mqtt_event"].payload["id"], "evt-1")

    def test_get_context_at_frame_only_when_no_mqtt_match(self) -> None:
        cam = self._make_camera()
        target = datetime.now(timezone.utc)
        cam.frame_buffer.append(
            BufferedFrame(timestamp=target, jpeg_bytes=b"frame-bytes", width=10, height=10)
        )
        cam.mqtt_buffer.append(
            BufferedMqttEvent(timestamp=target + timedelta(seconds=5), payload={"id": "evt-far"})
        )

        ctx = cam.get_context_at(target, tolerance_ms=100)
        self.assertTrue(ctx["frame_found"])
        self.assertFalse(ctx["mqtt_found"])


if __name__ == "__main__":
    unittest.main()
