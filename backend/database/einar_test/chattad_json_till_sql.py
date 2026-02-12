#!/usr/bin/env python3
"""
Ingest com.axis.consolidated_track.v1.beta JSON payloads into SQLite.

Usage examples:
  # 1) Read one JSON per line from stdin and store in db
  cat payloads.txt | python ingest_consolidated_tracks.py tracks.sqlite

  # 2) Subscribe and pipe directly (example)
  # mosquitto_sub -h 10.255.255.1 -p 1883 -t consolidated | python ingest_consolidated_tracks.py tracks.sqlite
"""

from __future__ import annotations

import json
import sqlite3
import sys
from typing import Any, Dict, Iterable, Optional, Tuple


DDL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS consolidated_tracks (
  id            TEXT PRIMARY KEY,
  channel_id    INTEGER,             -- sometimes present in some producers; nullable
  start_time    TEXT,                -- ISO8601
  end_time      TEXT,
  duration_s    REAL,
  end_reason    TEXT,
  raw_json      TEXT NOT NULL,
  received_at   TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS consolidated_track_images (
  track_id        TEXT PRIMARY KEY REFERENCES consolidated_tracks(id) ON DELETE CASCADE,
  timestamp       TEXT,
  bb_left         REAL,
  bb_top          REAL,
  bb_right        REAL,
  bb_bottom       REAL,
  image_base64    TEXT               -- may be huge; consider moving to BLOB later
);

CREATE TABLE IF NOT EXISTS consolidated_track_observations (
  track_id      TEXT NOT NULL REFERENCES consolidated_tracks(id) ON DELETE CASCADE,
  idx           INTEGER NOT NULL,
  timestamp     TEXT NOT NULL,
  bb_left       REAL NOT NULL,
  bb_top        REAL NOT NULL,
  bb_right      REAL NOT NULL,
  bb_bottom     REAL NOT NULL,
  PRIMARY KEY (track_id, idx)
);

CREATE INDEX IF NOT EXISTS idx_ct_time
  ON consolidated_tracks(start_time, end_time);

CREATE INDEX IF NOT EXISTS idx_obs_track_time
  ON consolidated_track_observations(track_id, timestamp);
"""


def _extract_json_object(line: str) -> Optional[str]:
    """
    Robustly extract the first top-level JSON object from a line.

    Handles cases like:
      "topic: {...}"
      "INFO ... {...} ..."
    Returns None if no plausible JSON object found.
    """
    s = line.strip()
    if not s:
        return None
    l = s.find("{")
    r = s.rfind("}")
    if l == -1 or r == -1 or r <= l:
        return None
    candidate = s[l : r + 1].strip()
    # quick sanity: must start/end with braces
    if not (candidate.startswith("{") and candidate.endswith("}")):
        return None
    return candidate


def _get_bbox(d: Dict[str, Any], key: str = "bounding_box") -> Optional[Tuple[float, float, float, float]]:
    """
    Extract {left, top, right, bottom} -> tuple, or None if missing/invalid.
    """
    bb = d.get(key)
    if not isinstance(bb, dict):
        return None
    try:
        left = float(bb["left"])
        top = float(bb["top"])
        right = float(bb["right"])
        bottom = float(bb["bottom"])
        return left, top, right, bottom
    except Exception:
        return None


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)
    conn.commit()


def ingest_payload(conn: sqlite3.Connection, payload: Dict[str, Any], raw_json: str) -> None:
    """
    Insert one consolidated_track payload into the DB.
    """
    track_id = payload.get("id")
    if not isinstance(track_id, str) or not track_id:
        raise ValueError("payload missing string field 'id'")

    channel_id = payload.get("channel_id")
    if channel_id is not None:
        try:
            channel_id = int(channel_id)
        except Exception:
            channel_id = None

    start_time = payload.get("start_time")
    end_time = payload.get("end_time")
    duration_s = payload.get("duration")
    end_reason = payload.get("end_reason")

    # Insert/Upsert track (keep latest raw_json)
    conn.execute(
        """
        INSERT INTO consolidated_tracks (id, channel_id, start_time, end_time, duration_s, end_reason, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          channel_id  = COALESCE(excluded.channel_id, consolidated_tracks.channel_id),
          start_time  = COALESCE(excluded.start_time, consolidated_tracks.start_time),
          end_time    = COALESCE(excluded.end_time, consolidated_tracks.end_time),
          duration_s  = COALESCE(excluded.duration_s, consolidated_tracks.duration_s),
          end_reason  = COALESCE(excluded.end_reason, consolidated_tracks.end_reason),
          raw_json    = excluded.raw_json
        """,
        (
            track_id,
            channel_id,
            start_time if isinstance(start_time, str) else None,
            end_time if isinstance(end_time, str) else None,
            float(duration_s) if isinstance(duration_s, (int, float)) else None,
            end_reason if isinstance(end_reason, str) else None,
            raw_json,
        ),
    )

    # Image (optional)
    image = payload.get("image")
    if isinstance(image, dict):
        img_ts = image.get("timestamp") if isinstance(image.get("timestamp"), str) else None
        img_data = image.get("data") if isinstance(image.get("data"), str) else None

        # In this beta payload, image uses "bounding_box" (not crop_box)
        bbox = _get_bbox(image, key="bounding_box")
        if bbox is None:
            # some variants might use crop_box
            bbox = _get_bbox(image, key="crop_box")

        if bbox is not None or img_ts is not None or img_data is not None:
            bb_left, bb_top, bb_right, bb_bottom = (bbox if bbox else (None, None, None, None))
            conn.execute(
                """
                INSERT INTO consolidated_track_images
                  (track_id, timestamp, bb_left, bb_top, bb_right, bb_bottom, image_base64)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(track_id) DO UPDATE SET
                  timestamp    = COALESCE(excluded.timestamp, consolidated_track_images.timestamp),
                  bb_left      = COALESCE(excluded.bb_left, consolidated_track_images.bb_left),
                  bb_top       = COALESCE(excluded.bb_top, consolidated_track_images.bb_top),
                  bb_right     = COALESCE(excluded.bb_right, consolidated_track_images.bb_right),
                  bb_bottom    = COALESCE(excluded.bb_bottom, consolidated_track_images.bb_bottom),
                  image_base64 = COALESCE(excluded.image_base64, consolidated_track_images.image_base64)
                """,
                (track_id, img_ts, bb_left, bb_top, bb_right, bb_bottom, img_data),
            )

    # Observations (optional)
    obs = payload.get("observations")
    if isinstance(obs, list) and obs:
        # Replace observations for this track_id (simplest & consistent if we re-receive)
        conn.execute("DELETE FROM consolidated_track_observations WHERE track_id = ?", (track_id,))

        rows = []
        for i, item in enumerate(obs):
            if not isinstance(item, dict):
                continue
            ts = item.get("timestamp")
            if not isinstance(ts, str):
                continue
            bbox = _get_bbox(item, key="bounding_box")
            if bbox is None:
                continue
            left, top, right, bottom = bbox
            rows.append((track_id, i, ts, left, top, right, bottom))

        conn.executemany(
            """
            INSERT INTO consolidated_track_observations
              (track_id, idx, timestamp, bb_left, bb_top, bb_right, bb_bottom)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def ingest_lines(conn: sqlite3.Connection, lines: Iterable[str]) -> Tuple[int, int]:
    """
    Returns (ok_count, fail_count)
    """
    ok = 0
    fail = 0

    # One transaction for speed
    with conn:
        for line in lines:
            jtxt = _extract_json_object(line)
            if not jtxt:
                continue  # ignore non-json/noise lines
            try:
                payload = json.loads(jtxt)
                if not isinstance(payload, dict):
                    raise ValueError("top-level JSON is not an object")
                ingest_payload(conn, payload, jtxt)
                ok += 1
            except Exception as e:
                fail += 1
                # write minimal error to stderr, keep going
                sys.stderr.write(f"[WARN] failed to ingest line: {e}\n")

    return ok, fail


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: ingest_consolidated_tracks.py <db.sqlite>", file=sys.stderr)
        return 2

    db_path = sys.argv[1]
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")

    ensure_schema(conn)

    ok, fail = ingest_lines(conn, sys.stdin)
    print(f"Ingested OK: {ok}, failed: {fail}", file=sys.stderr)
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
