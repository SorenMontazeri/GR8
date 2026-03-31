from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import base64
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3

import cv2
import uvicorn

DB_PATH = Path(__file__).with_name("analysis.sqlite")
RECORDINGS_DIR = str(Path(__file__).resolve().parent.parent / "recordings/1")
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/image/{name}")
def get_image(name: str):
    #Hämtar en bild från en request från frontend. Indata är en tagg/description som söks på, och det returnar en bas64 sträng med bilden
    ts = timestamp_from_description(name)
    if ts is None:
        raise HTTPException(status_code=404, detail="No timestamp for this description")

    t = datetime.fromisoformat(ts)
    return {"name": name, "image": image_from_timestamp(t)}


def create_database() -> None:
    # Skapar alla tabeller som behövs av backend (även gamla analysis för bakåtkompabilitet).
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            description TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sequence_description_uniform (
            timestamp_start TEXT PRIMARY KEY,
            timestamp_end TEXT NOT NULL,
            created_at TEXT NOT NULL,
            timestamps_json TEXT NOT NULL,
            llm_description TEXT NOT NULL,
            description_embedding BLOB,
            feedback INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS sequence_description_varied (
            timestamp_start TEXT PRIMARY KEY,
            timestamp_end TEXT NOT NULL,
            created_at TEXT NOT NULL,
            timestamps_json TEXT NOT NULL,
            llm_description TEXT NOT NULL,
            description_embedding BLOB,
            feedback INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS snapshot_description (
            timestamp TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            llm_description TEXT NOT NULL,
            description_embedding BLOB,
            feedback INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS full_frame_description (
            timestamp TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            llm_description TEXT NOT NULL,
            description_embedding BLOB,
            feedback INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS description_group (
            timestamp_start TEXT PRIMARY KEY,
            timestamp_end TEXT NOT NULL,
            sequence_description_uniform_id TEXT,
            sequence_description_varied_id TEXT,
            snapshot_description_id TEXT,
            full_frame_description_id TEXT,
            FOREIGN KEY (sequence_description_uniform_id)
                REFERENCES sequence_description_uniform(timestamp_start),
            FOREIGN KEY (sequence_description_varied_id)
                REFERENCES sequence_description_varied(timestamp_start),
            FOREIGN KEY (snapshot_description_id)
                REFERENCES snapshot_description(timestamp),
            FOREIGN KEY (full_frame_description_id)
                REFERENCES full_frame_description(timestamp)
        );
        """
    )
    conn.commit()
    conn.close()


def _to_iso(ts: datetime | str) -> str:
    if isinstance(ts, datetime):
        return ts.isoformat()
    return ts


def save_sequence_description_uniform(
    timestamp_start: datetime | str,
    timestamp_end: datetime | str,
    created_at: datetime | str,
    timestamps: list[datetime | str],
    llm_description: str,
    description_embedding: bytes | None = None,
    feedback: int = 0,
) -> str:
    create_database()
    start_iso = _to_iso(timestamp_start)
    end_iso = _to_iso(timestamp_end)
    timestamps_json = json.dumps([_to_iso(ts) for ts in timestamps])

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO sequence_description_uniform (
            timestamp_start, timestamp_end, created_at, timestamps_json,
            llm_description, description_embedding, feedback
        ) VALUES (?, ?, ?, ?, ?, ?, ?);
        """,
        (start_iso, end_iso, _to_iso(created_at), timestamps_json, llm_description, description_embedding, feedback),
    )
    conn.commit()
    conn.close()
    return start_iso


def save_sequence_description_varied(
    timestamp_start: datetime | str,
    timestamp_end: datetime | str,
    created_at: datetime | str,
    timestamps: list[datetime | str],
    llm_description: str,
    description_embedding: bytes | None = None,
    feedback: int = 0,
) -> str:
    create_database()
    start_iso = _to_iso(timestamp_start)
    end_iso = _to_iso(timestamp_end)
    timestamps_json = json.dumps([_to_iso(ts) for ts in timestamps])

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO sequence_description_varied (
            timestamp_start, timestamp_end, created_at, timestamps_json,
            llm_description, description_embedding, feedback
        ) VALUES (?, ?, ?, ?, ?, ?, ?);
        """,
        (start_iso, end_iso, _to_iso(created_at), timestamps_json, llm_description, description_embedding, feedback),
    )
    conn.commit()
    conn.close()
    return start_iso


def save_snapshot_description(
    timestamp: datetime | str,
    created_at: datetime | str,
    llm_description: str,
    description_embedding: bytes | None = None,
    feedback: int = 0,
) -> str:
    create_database()
    ts_iso = _to_iso(timestamp)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO snapshot_description (
            timestamp, created_at, llm_description, description_embedding, feedback
        ) VALUES (?, ?, ?, ?, ?);
        """,
        (ts_iso, _to_iso(created_at), llm_description, description_embedding, feedback),
    )
    conn.commit()
    conn.close()
    return ts_iso


def save_full_frame_description(
    timestamp: datetime | str,
    created_at: datetime | str,
    llm_description: str,
    description_embedding: bytes | None = None,
    feedback: int = 0,
) -> str:
    create_database()
    ts_iso = _to_iso(timestamp)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO full_frame_description (
            timestamp, created_at, llm_description, description_embedding, feedback
        ) VALUES (?, ?, ?, ?, ?);
        """,
        (ts_iso, _to_iso(created_at), llm_description, description_embedding, feedback),
    )
    conn.commit()
    conn.close()
    return ts_iso


def save_description_group(
    timestamp_start: datetime | str,
    timestamp_end: datetime | str,
    sequence_description_uniform_id: datetime | str | None = None,
    sequence_description_varied_id: datetime | str | None = None,
    snapshot_description_id: datetime | str | None = None,
    full_frame_description_id: datetime | str | None = None,
) -> str:
    create_database()
    start_iso = _to_iso(timestamp_start)
    end_iso = _to_iso(timestamp_end)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO description_group (
            timestamp_start, timestamp_end,
            sequence_description_uniform_id, sequence_description_varied_id,
            snapshot_description_id, full_frame_description_id
        ) VALUES (?, ?, ?, ?, ?, ?);
        """,
        (
            start_iso,
            end_iso,
            _to_iso(sequence_description_uniform_id) if sequence_description_uniform_id else None,
            _to_iso(sequence_description_varied_id) if sequence_description_varied_id else None,
            _to_iso(snapshot_description_id) if snapshot_description_id else None,
            _to_iso(full_frame_description_id) if full_frame_description_id else None,
        ),
    )
    conn.commit()
    conn.close()
    return start_iso


def save_description_bundle(
    timestamp_start: datetime | str,
    timestamp_end: datetime | str,
    created_at: datetime | str,
    uniform_llm_description: str,
    varied_llm_description: str,
    snapshot_llm_description: str,
    full_frame_llm_description: str,
    uniform_timestamps: list[datetime | str] | None = None,
    varied_timestamps: list[datetime | str] | None = None,
    snapshot_timestamp: datetime | str | None = None,
    full_frame_timestamp: datetime | str | None = None,
) -> dict[str, str]:
    start_iso = _to_iso(timestamp_start)
    end_iso = _to_iso(timestamp_end)

    if uniform_timestamps is None:
        uniform_timestamps = [start_iso, end_iso]
    if varied_timestamps is None:
        varied_timestamps = [start_iso, end_iso]
    if snapshot_timestamp is None:
        snapshot_timestamp = start_iso
    if full_frame_timestamp is None:
        full_frame_timestamp = end_iso

    uniform_id = save_sequence_description_uniform(
        timestamp_start=start_iso,
        timestamp_end=end_iso,
        created_at=created_at,
        timestamps=uniform_timestamps,
        llm_description=uniform_llm_description,
        description_embedding=uniform_embedding,
    )
    varied_id = save_sequence_description_varied(
        timestamp_start=start_iso,
        timestamp_end=end_iso,
        created_at=created_at,
        timestamps=varied_timestamps,
        llm_description=varied_llm_description,
        description_embedding=varied_embedding,
    )
    snapshot_id = save_snapshot_description(
        timestamp=snapshot_timestamp,
        created_at=created_at,
        llm_description=snapshot_llm_description,
        description_embedding=snapshot_embedding,
    )
    full_frame_id = save_full_frame_description(
        timestamp=full_frame_timestamp,
        created_at=created_at,
        llm_description=full_frame_llm_description,
        description_embedding=full_frame_embedding,
    )
    group_id = save_description_group(
        timestamp_start=start_iso,
        timestamp_end=end_iso,
        sequence_description_uniform_id=uniform_id,
        sequence_description_varied_id=varied_id,
        snapshot_description_id=snapshot_id,
        full_frame_description_id=full_frame_id,
    )


def image_from_timestamp(t, clip=10):
    # Söker igenom alla videofiler och kollar på filnamnen. Om filens namn visar att den innehåller det timestamps som söks, så öppna den filen, 
    # ta ut den framen som söks efter och konvertera den till bas64. 
    for f in os.listdir(RECORDINGS_DIR):
        try:
            s = datetime.strptime(f, "D%Y-%m-%d-T%H-%M-%S.mp4")
            if s <= t < s + timedelta(seconds=clip):
                p = os.path.join(RECORDINGS_DIR, f)
                cap = cv2.VideoCapture(p)
                cap.set(cv2.CAP_PROP_POS_FRAMES, int((t - s).total_seconds() * cap.get(cv2.CAP_PROP_FPS)))
                ok, frame = cap.read()
                cap.release()
                if not ok:
                    raise RuntimeError("Kunde inte läsa frame")

                # Encode to JPEG in memory
                _, buffer = cv2.imencode(".jpg", frame)
                return base64.b64encode(buffer).decode("utf-8")
        except:
            pass

    raise FileNotFoundError("Ingen matchande video")

if __name__ == "__main__":
    uvicorn.run("database:app", reload=True)
