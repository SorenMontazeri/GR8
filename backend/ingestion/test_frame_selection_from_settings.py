import base64
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import sys
import types

# ------------------------------------------------------------
# Mock database.database to avoid loading sentence_transformers
# ------------------------------------------------------------
mock_database = types.ModuleType("database")
mock_database_database = types.ModuleType("database.database")

def fake_save_description_bundle(*args, **kwargs):
    print("[MOCK] save_description_bundle called")

mock_database_database.save_description_bundle = fake_save_description_bundle

sys.modules["database"] = mock_database
sys.modules["database.database"] = mock_database_database

import sys
import types

# ------------------------------------------------------------
# Mock database.database
# ------------------------------------------------------------
mock_database = types.ModuleType("database")
mock_database_database = types.ModuleType("database.database")

def fake_save_description_bundle(*args, **kwargs):
    print("[MOCK] save_description_bundle called")

mock_database_database.save_description_bundle = fake_save_description_bundle

sys.modules["database"] = mock_database
sys.modules["database.database"] = mock_database_database


# ------------------------------------------------------------
# Mock ingestion.record_ffmpeg
# ------------------------------------------------------------
mock_record_ffmpeg = types.ModuleType("ingestion.record_ffmpeg")

def fake_start_recording_ffmpeg(*args, **kwargs):
    print("[MOCK] start_recording_ffmpeg called")
    return None

def fake_stop_recording(*args, **kwargs):
    print("[MOCK] stop_recording called")

mock_record_ffmpeg.start_recording_ffmpeg = fake_start_recording_ffmpeg
mock_record_ffmpeg.stop_recording = fake_stop_recording

sys.modules["ingestion.record_ffmpeg"] = mock_record_ffmpeg


from camera import Camera


# ------------------------------------------------------------------
# Fake analysis client (no network calls)
# ------------------------------------------------------------------
class FakeAnalysisClient:
    async def query_description_open(self, images):
        return {"description": f"fake analysis for {len(images)} images"}


# ------------------------------------------------------------------
# Fake MQTT message
# ------------------------------------------------------------------
class FakeMsg:
    def __init__(self, payload: dict):
        self.payload = json.dumps(payload).encode("utf-8")


def run_test(settings_file: str):
    print(f"\n=== Running test with {settings_file} ===")

    # Instantiate camera (we won't start RTSP/MQTT for real)
    camera = Camera(
        camera_id="test",
        rtsp_url="rtsp://dummy",
        ffmpeg="ffmpeg",
        broker_host="localhost",
        broker_port=1883,
        analysis_client=FakeAnalysisClient(),
    )

    # Override settings loaded in __init__
    settings_path = Path(__file__).parent.parent / "database" / settings_file
    with open(settings_path, "r", encoding="utf-8") as f:
        camera.settings = json.load(f)

    # Fake buffered frame
    now = datetime.now(timezone.utc)
    fake_frame = camera.frame_buffer = None

    camera.get_hot_buffer_frame_at = lambda ts: type(
        "Frame",
        (),
        {
            "timestamp": ts,
            "jpeg_bytes": b"fake_jpeg",
            "width": 640,
            "height": 480,
        },
    )()

    # Fake MQTT payload
    fake_msg = FakeMsg(
        {
            "start_time": now.isoformat(),
            "end_time": (now + timedelta(seconds=20)).isoformat(),
            "image": {"data": base64.b64encode(b"snapshot").decode()},
        }
    )

    # Call function under test
    camera.on_message(None, None, fake_msg)


if __name__ == "__main__":
    run_test("settings.json")