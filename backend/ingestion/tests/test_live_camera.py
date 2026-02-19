from __future__ import annotations

import importlib.util
import json
import sys
import types
import unittest
from datetime import datetime, timezone


def _ensure_stub_modules() -> None:
    if importlib.util.find_spec("cv2") is None:
        cv2 = types.ModuleType("cv2")
        cv2.IMWRITE_JPEG_QUALITY = 1
        cv2.INTER_AREA = 3
        sys.modules["cv2"] = cv2

    if importlib.util.find_spec("imageio_ffmpeg") is None:
        imageio_ffmpeg = types.ModuleType("imageio_ffmpeg")
        imageio_ffmpeg.get_ffmpeg_exe = lambda: "ffmpeg"
        sys.modules["imageio_ffmpeg"] = imageio_ffmpeg

    if importlib.util.find_spec("paho") is None:
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


_ensure_stub_modules()

from ingestion.camera import BufferedFrame, Camera, FrameRingBuffer  # noqa: E402
from ingestion.dispatch.dispatcher import DirectDispatcher  # noqa: E402
from ingestion.ingestion_service import IngestionService  # noqa: E402
from ingestion.source.replay_reader import RawEvent  # noqa: E402


class _Msg:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload


class _SpyIngestionService:
    def __init__(self) -> None:
        self.calls: list[RawEvent] = []

    def handle_raw_event(self, raw_event: RawEvent) -> bool:
        self.calls.append(raw_event)
        return True


class CameraOnMessageTests(unittest.TestCase):
    def _make_camera(self) -> Camera:
        cam = Camera.__new__(Camera)
        cam.camera_id = "cam-1"
        return cam

    def test_on_message_valid_json_creates_live_raw_event(self) -> None:
        cam = self._make_camera()
        spy = _SpyIngestionService()
        cam.ingestion_service = spy

        payload = {"id": "track-1", "channel_id": 1, "start_time": "2026-02-19T10:00:00Z"}
        msg = _Msg(json.dumps(payload).encode("utf-8"))

        cam.on_message(None, None, msg)

        self.assertEqual(len(spy.calls), 1)
        raw_event = spy.calls[0]
        self.assertEqual(raw_event.raw, payload)
        self.assertEqual(raw_event.source, "live")
        self.assertIsNone(raw_event.replay_seq)
        self.assertIsNone(raw_event.replay_file)

    def test_on_message_invalid_json_is_handled(self) -> None:
        cam = self._make_camera()
        spy = _SpyIngestionService()
        cam.ingestion_service = spy

        cam.on_message(None, None, _Msg(b"{"))
        cam.on_message(None, None, _Msg(b""))

        self.assertEqual(len(spy.calls), 0)

    def test_on_message_live_payload_dispatches_internal_event(self) -> None:
        cam = self._make_camera()
        dispatched = []
        cam.ingestion_service = IngestionService(
            enable_raw_store=False,
            dispatcher=DirectDispatcher(dispatched.append),
        )

        payload = {
            "id": "track-live-123",
            "channel_id": 1,
            "start_time": "2026-02-19T10:00:00Z",
            "end_time": "2026-02-19T10:00:01Z",
            "duration": 1.0,
            "classes": [{"type": "Human", "score": 0.9}],
            "parts": [{"object_track_id": "unused-for-now"}],
        }
        msg = _Msg(json.dumps(payload).encode("utf-8"))

        cam.on_message(None, None, msg)

        self.assertEqual(len(dispatched), 1)
        event = dispatched[0]
        self.assertEqual(event.track_id, "track-live-123")
        self.assertEqual(event.source, "live")


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
