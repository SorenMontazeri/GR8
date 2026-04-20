from __future__ import annotations

import base64
import importlib.util
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException


MODULE_PATH = Path(__file__).with_name("database.py")


def load_database_module():
    spec = importlib.util.spec_from_file_location("database_under_test", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DatabaseUnitTests(unittest.TestCase):
    def setUp(self):
        self.db_module = load_database_module()

    def test_create_database_creates_analysis_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.db_module.DB_PATH = Path(tmp) / "analysis.sqlite"
            self.db_module.create_database()

            conn = sqlite3.connect(self.db_module.DB_PATH)
            cols = [row[1] for row in conn.execute("PRAGMA table_info(analysis);").fetchall()]
            conn.close()

            self.assertEqual(cols, ["id", "created_at", "description"])

    def test_save_analysis_persists_row_and_returns_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.db_module.DB_PATH = Path(tmp) / "analysis.sqlite"
            created_at = datetime(2026, 3, 2, 10, 30, 45)

            row_id = self.db_module.save_analysis(created_at, "car in driveway")

            self.assertEqual(row_id, 1)
            self.assertEqual(
                self.db_module.timestamp_from_description("car in driveway"),
                created_at.isoformat(),
            )

    def test_timestamp_from_description_returns_none_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.db_module.DB_PATH = Path(tmp) / "analysis.sqlite"
            self.assertIsNone(self.db_module.timestamp_from_description("not present"))

    def test_get_image_raises_404_without_timestamp(self):
        with patch.object(self.db_module, "timestamp_from_description", return_value=None):
            with self.assertRaises(HTTPException) as ctx:
                self.db_module.get_image("missing description")

            self.assertEqual(ctx.exception.status_code, 404)
            self.assertEqual(ctx.exception.detail, "No timestamp for this description")

    def test_get_image_returns_name_and_encoded_image(self):
        iso_timestamp = "2026-03-02T12:15:00"
        seen = {}

        def fake_image_from_timestamp(t):
            seen["timestamp"] = t
            return "encoded-jpg"

        with patch.object(self.db_module, "timestamp_from_description", return_value=iso_timestamp), patch.object(
            self.db_module, "image_from_timestamp", side_effect=fake_image_from_timestamp
        ):
            result = self.db_module.get_image("person walking")

        self.assertEqual(result, {"name": "person walking", "image": "encoded-jpg"})
        self.assertEqual(seen["timestamp"], datetime.fromisoformat(iso_timestamp))

    def test_image_from_timestamp_returns_base64_of_matching_video_frame(self):
        start_file = "D2026-03-02-T12-00-00.mp4"
        target_time = datetime(2026, 3, 2, 12, 0, 3)
        captured = {}

        class FakeCapture:
            def __init__(self, path):
                self.path = path
                self.set_calls = []
                self.released = False

            def set(self, prop, value):
                self.set_calls.append((prop, value))

            def get(self, _prop):
                return 25.0

            def read(self):
                return True, object()

            def release(self):
                self.released = True

        def fake_video_capture(path):
            cap = FakeCapture(path)
            captured["cap"] = cap
            return cap

        class FakeCV2:
            CAP_PROP_POS_FRAMES = 1
            CAP_PROP_FPS = 2
            VideoCapture = staticmethod(fake_video_capture)

            @staticmethod
            def imencode(_ext, _frame):
                return True, b"jpeg-bytes"

        with tempfile.TemporaryDirectory() as tmp, patch.object(self.db_module, "RECORDINGS_DIR", tmp), patch.object(
            self.db_module.os, "listdir", return_value=[start_file]
        ), patch.object(self.db_module, "cv2", FakeCV2):
            image_b64 = self.db_module.image_from_timestamp(target_time, clip=10)

        self.assertEqual(image_b64, base64.b64encode(b"jpeg-bytes").decode("utf-8"))
        self.assertEqual(captured["cap"].path, str(Path(tmp) / start_file))
        self.assertEqual(captured["cap"].set_calls, [(FakeCV2.CAP_PROP_POS_FRAMES, 75)])
        self.assertTrue(captured["cap"].released)

    def test_image_from_timestamp_raises_when_no_matching_video(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(self.db_module, "RECORDINGS_DIR", tmp), patch.object(
            self.db_module.os, "listdir", return_value=["bad-format-name.mp4"]
        ):
            with self.assertRaisesRegex(FileNotFoundError, "Ingen matchande video"):
                self.db_module.image_from_timestamp(datetime(2026, 3, 2, 12, 0, 0), clip=10)

    def test_create_database_adds_number_of_tokens_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.db_module.DB_PATH = Path(tmp) / "analysis.sqlite"
            self.db_module.create_database()

            conn = sqlite3.connect(self.db_module.DB_PATH)
            uniform_cols = [row[1] for row in conn.execute("PRAGMA table_info(sequence_description_uniform);").fetchall()]
            varied_cols = [row[1] for row in conn.execute("PRAGMA table_info(sequence_description_varied);").fetchall()]
            snapshot_cols = [row[1] for row in conn.execute("PRAGMA table_info(snapshot_description);").fetchall()]
            full_frame_cols = [row[1] for row in conn.execute("PRAGMA table_info(full_frame_description);").fetchall()]
            conn.close()

            self.assertIn("number_of_tokens", uniform_cols)
            self.assertIn("number_of_tokens", varied_cols)
            self.assertIn("number_of_tokens", snapshot_cols)
            self.assertIn("number_of_tokens", full_frame_cols)

    def test_save_description_bundle_and_get_events_include_number_of_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.db_module.DB_PATH = Path(tmp) / "analysis.sqlite"
            start = datetime(2026, 3, 2, 10, 0, 0)
            end = datetime(2026, 3, 2, 10, 0, 10)
            created_at = datetime(2026, 3, 2, 10, 0, 11)
            snapshot_b64 = base64.b64encode(b"snapshot").decode("utf-8")

            with patch.object(self.db_module, "embed", return_value=[0.1, 0.2, 0.3]):
                ids = self.db_module.save_description_bundle(
                    timestamp_start=start,
                    timestamp_end=end,
                    created_at=created_at,
                    uniform_llm_description="uniform",
                    varied_llm_description="varied",
                    snapshot_llm_description="snapshot",
                    full_frame_llm_description="full_frame",
                    uniform_timestamps=[start, end],
                    varied_timestamps=[start, end],
                    snapshot_timestamp=start,
                    full_frame_timestamp=end,
                    snapshot_image_base64=snapshot_b64,
                    uniform_number_of_tokens=11,
                    varied_number_of_tokens=22,
                    snapshot_number_of_tokens=33,
                    full_frame_number_of_tokens=44,
                )

            with patch.object(
                self.db_module,
                "find_best_event",
                return_value={
                    "group_id": ids["description_group_id"],
                    "score": 0.99,
                    "matched_type": "uniform",
                    "matched_row_id": ids["sequence_description_uniform_id"],
                },
            ), patch.object(self.db_module, "_images_from_timestamps", return_value=[]), patch.object(
                self.db_module, "_safe_image_from_iso", return_value=None
            ):
                result = self.db_module.get_events("person")

            self.assertEqual(result["uniform"]["number_of_tokens"], 11)
            self.assertEqual(result["varied"]["number_of_tokens"], 22)
            self.assertEqual(result["snapshot"]["number_of_tokens"], 33)
            self.assertEqual(result["full_frame"]["number_of_tokens"], 44)


if __name__ == "__main__":
    unittest.main()
