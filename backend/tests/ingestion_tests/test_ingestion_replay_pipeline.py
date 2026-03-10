from __future__ import annotations

"""
Replay pipeline test (fil -> validering -> mapping -> InternalEvent callback).

Kopplat till krav:
- F03 "Systemet ska kunna hantera inspelad data på samma sätt som live-data."
- F06 "Systemet ska kunna köras på inspelad data. Det inspelade scenariot ska kunna köras flera gånger."
- F02 "Systemet ska kunna logga felaktig metadata (flagga för tom/dålig/ogiltig data)."

Testnivå:
- Integrationstest

Varför testet finns:
- Verifiera att replay-data går igenom samma ingest-pipeline som live-data.
- Verifiera att ogiltiga händelser filtreras utan krasch.

Vad testet verifierar:
- run_replay skapar och skickar InternalEvent för giltig object-track payload.
- Replay-körning ger stabilt resultat över flera körningar.
- Ogiltig/tom payload räknas inte som ett lyckat event.

Förutsättningar:
- Inga externa beroenden krävs.

Vad man ska titta efter i terminalen:
1. Testet passerar.
2. Event-count och callback-count stämmer enligt assertions.

Vad man ska titta efter i filsystemet / systemet:
- Inga filer behöver skapas för detta test.

För att köra testet:
cd GR8/backend
python3 -m pytest tests/ingestion_tests/test_ingestion_replay_pipeline.py -v
"""

import json
import tempfile
import unittest
from pathlib import Path

from ingestion.ingestion_service import IngestionService


class ReplayPipelineTests(unittest.TestCase):
    def _write_temp_json(self, payload) -> str:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as fp:
            json.dump(payload, fp)
            return fp.name

    def test_run_replay_valid_object_track_creates_internal_event(self) -> None:
        replay_path = self._write_temp_json(
            {
                "id": "track-123",
                "channel_id": 1,
                "start_time": "2026-02-09T03:44:54.382068Z",
                "end_time": "2026-02-09T03:44:54.782066Z",
                "duration": 0.4,
                "classes": [{"type": "Human", "score": 0.9}],
                "path": [{"timestamp": "2026-02-09T03:44:54.382068Z"}],
                "parts": [{"object_track_id": "track-123"}],
            }
        )
        self.addCleanup(lambda: Path(replay_path).unlink(missing_ok=True))

        collected_events = []
        svc = IngestionService(enable_raw_store=False, on_internal_event=collected_events.append)
        count = svc.run_replay(replay_path)

        self.assertEqual(count, 1)
        self.assertEqual(len(collected_events), 1)
        event = collected_events[0]
        self.assertEqual(event.track_id, "track-123")
        self.assertEqual(event.camera_id, "1")
        self.assertEqual(event.source, "replay")
        self.assertEqual(event.event_type, "object_track")

    def test_run_replay_mixed_valid_and_invalid_events(self) -> None:
        replay_path = self._write_temp_json(
            [
                {},
                {"not": "an-object-track"},
                {
                    "id": "track-ok",
                    "channel_id": 7,
                    "start_time": "2026-02-09T03:44:54.382068Z",
                    "classes": [{"type": "Human", "score": 0.8}],
                    "path": [{"timestamp": "2026-02-09T03:44:54.382068Z"}],
                    "parts": [{"object_track_id": "track-ok"}],
                },
            ]
        )
        self.addCleanup(lambda: Path(replay_path).unlink(missing_ok=True))

        collected_events = []
        svc = IngestionService(enable_raw_store=False, on_internal_event=collected_events.append)

        first_count = svc.run_replay(replay_path)
        second_count = svc.run_replay(replay_path)

        self.assertEqual(first_count, 1)
        self.assertEqual(second_count, 1)
        self.assertEqual(len(collected_events), 2)
        self.assertTrue(all(ev.track_id == "track-ok" for ev in collected_events))


if __name__ == "__main__":
    unittest.main()
