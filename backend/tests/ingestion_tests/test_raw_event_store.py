from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ingestion.source.replay_reader import RawEvent
from ingestion.storage.raw_event_store import RawEventStore


class RawEventStoreTests(unittest.TestCase):
    def test_can_write_to_explicit_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "nested" / "live_events.jsonl"
            store = RawEventStore(output_path=output_path)

            store.append(
                RawEvent(
                    raw={"start_time": "2026-05-03T20:01:38Z", "id": "abc"},
                    received_at=datetime(2026, 5, 3, 20, 2, 0, tzinfo=timezone.utc),
                    source="live",
                )
            )

            self.assertTrue(output_path.exists())
            lines = output_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            row = json.loads(lines[0])
            self.assertEqual(row["source"], "live")
            self.assertEqual(row["raw"]["id"], "abc")

