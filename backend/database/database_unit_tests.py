from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


def _ensure_stub_modules() -> None:
    sentence_transformers = types.ModuleType("sentence_transformers")

    class _StubSentenceTransformer:
        def __init__(self, *_args, **_kwargs) -> None:
            return None

        def encode(self, _text: str, normalize_embeddings: bool = True) -> list[float]:
            return [1.0, 0.0]

        def save(self, *_args, **_kwargs) -> None:
            return None

    sentence_transformers.SentenceTransformer = _StubSentenceTransformer
    sys.modules["sentence_transformers"] = sentence_transformers

    if "cv2" not in sys.modules:
        sys.modules["cv2"] = types.ModuleType("cv2")


def _load_database_module():
    _ensure_stub_modules()
    module_path = Path(__file__).with_name("database.py")
    spec = importlib.util.spec_from_file_location("database_module_under_test", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


database_module = _load_database_module()
client = TestClient(database_module.app)


class DatabaseApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        database_module.DB_PATH = Path(self.temp_dir.name) / "analysis_test.sqlite"
        database_module.create_database()

    def _seed_rows(self) -> dict[str, int | str]:
        start = "2026-04-08T10:00:00+00:00"
        end = "2026-04-08T10:00:05+00:00"
        created = "2026-04-08T10:01:00+00:00"

        uniform_id = database_module.save_sequence_description_uniform(
            timestamp_start=start,
            timestamp_end=end,
            created_at=created,
            timestamps=[start, end],
            llm_description="uniform desc",
            description_embedding=json.dumps([0.1, 0.2]),
        )
        varied_id = database_module.save_sequence_description_varied(
            timestamp_start=start,
            timestamp_end=end,
            created_at=created,
            timestamps=[start, end],
            llm_description="varied desc",
            description_embedding=json.dumps([0.2, 0.1]),
        )
        snapshot_id = database_module.save_snapshot_description(
            timestamp=start,
            created_at=created,
            llm_description="snapshot desc",
            snapshot_image_base64="snapshot-b64",
            description_embedding=json.dumps([0.3, 0.4]),
        )
        full_frame_id = database_module.save_full_frame_description(
            timestamp=end,
            created_at=created,
            llm_description="full frame desc",
            description_embedding=json.dumps([0.4, 0.3]),
        )
        group_id = database_module.save_description_group(
            timestamp_start=start,
            timestamp_end=end,
            sequence_description_uniform_id=uniform_id,
            sequence_description_varied_id=varied_id,
            snapshot_description_id=snapshot_id,
            full_frame_description_id=full_frame_id,
        )
        return {
            "start": start,
            "end": end,
            "group_id": group_id,
            "uniform_id": uniform_id,
        }

    def test_get_event_returns_payload_from_matching_group(self) -> None:
        seeded = self._seed_rows()

        with patch.object(
            database_module,
            "find_best_event",
            return_value={
                "group_id": seeded["group_id"],
                "score": 0.99,
                "matched_type": "uniform",
                "matched_row_id": seeded["uniform_id"],
            },
        ), patch.object(
            database_module,
            "_images_from_timestamps",
            side_effect=lambda timestamps: [f"img:{ts}" for ts in timestamps],
        ), patch.object(
            database_module,
            "_safe_image_from_iso",
            side_effect=lambda ts: f"frame:{ts}",
        ):
            response = client.get("/api/event/person")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["query"], "person")
        self.assertEqual(body["description_group"]["id"], seeded["group_id"])
        self.assertEqual(body["uniform"]["id"], seeded["uniform_id"])
        self.assertEqual(
            body["uniform"]["images"],
            [f"img:{seeded['start']}", f"img:{seeded['end']}"],
        )
        self.assertEqual(body["snapshot"]["image"], "snapshot-b64")
        self.assertEqual(body["full_frame"]["image"], f"frame:{seeded['end']}")

    def test_post_feedback_updates_uniform_feedback_value(self) -> None:
        seeded = self._seed_rows()

        response = client.post(
            "/api/feedback",
            json={"description_type": "uniform", "id": seeded["group_id"], "feedback": 1},
        )

        self.assertEqual(response.status_code, 204)

        conn = sqlite3.connect(database_module.DB_PATH)
        row = conn.execute(
            "SELECT feedback FROM sequence_description_uniform WHERE id = ?;",
            (seeded["uniform_id"],),
        ).fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row[0], 1)


if __name__ == "__main__":
    unittest.main()
