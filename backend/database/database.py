from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import base64
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3

import cv2
import uvicorn
from zoneinfo import ZoneInfo

import math
import re
import unicodedata
from collections import Counter

DB_PATH = Path(__file__).with_name("analysis.sqlite")
RECORDINGS_DIR = str(Path(__file__).resolve().parent.parent / "recordings/1")
RECORDINGS_TZ = ZoneInfo("Europe/Stockholm")
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FEEDBACK_TABLES = {
    "uniform": "sequence_description_uniform",
    "varied": "sequence_description_varied",
    "snapshot": "snapshot_description",
    "full_frame": "full_frame_description",
}


class FeedbackRequest(BaseModel):
    description_type: str
    id: int
    vote: str  # like / dislike


@app.get("/api/image/{name}")
def get_image(name: str):
    ts = timestamp_from_description(name)
    if ts is None:
        raise HTTPException(status_code=404, detail="No timestamp for this description")

    t = datetime.fromisoformat(ts)
    try:
        return {"name": name, "image": image_from_timestamp(t)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/feedback", status_code=204)
def post_feedback(payload: FeedbackRequest):
    vote = payload.vote.strip().lower()
    if vote not in ("like", "dislike"):
        raise HTTPException(status_code=400, detail="vote must be 'like' or 'dislike'")

    feedback_value = 1 if vote == "like" else -1
    update_feedback(payload.description_type, payload.id, feedback_value)


def update_feedback(description_type: str, item_id: int, feedback_value: int) -> None:
    table = FEEDBACK_TABLES.get(description_type.strip().lower())
    if table is None:
        raise HTTPException(
            status_code=400,
            detail="description_type must be one of: uniform, varied, snapshot, full_frame",
        )

    create_database()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(f"UPDATE {table} SET feedback = ? WHERE id = ?;", (feedback_value, item_id))
    conn.commit()
    updated = cur.rowcount
    conn.close()

    if updated == 0:
        raise HTTPException(status_code=404, detail=f"No row found with id={item_id} in {table}")


def create_database() -> None:
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp_start TEXT NOT NULL,
            timestamp_end TEXT NOT NULL,
            created_at TEXT NOT NULL,
            timestamps_json TEXT NOT NULL,
            llm_description TEXT NOT NULL,
            description_embedding BLOB,
            feedback INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS sequence_description_varied (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp_start TEXT NOT NULL,
            timestamp_end TEXT NOT NULL,
            created_at TEXT NOT NULL,
            timestamps_json TEXT NOT NULL,
            llm_description TEXT NOT NULL,
            description_embedding BLOB,
            feedback INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS snapshot_description (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            created_at TEXT NOT NULL,
            llm_description TEXT NOT NULL,
            description_embedding BLOB,
            feedback INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS full_frame_description (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            created_at TEXT NOT NULL,
            llm_description TEXT NOT NULL,
            description_embedding BLOB,
            feedback INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS description_group (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp_start TEXT NOT NULL,
            timestamp_end TEXT NOT NULL,
            sequence_description_uniform_id INTEGER,
            sequence_description_varied_id INTEGER,
            snapshot_description_id INTEGER,
            full_frame_description_id INTEGER,
            FOREIGN KEY (sequence_description_uniform_id)
                REFERENCES sequence_description_uniform(id),
            FOREIGN KEY (sequence_description_varied_id)
                REFERENCES sequence_description_varied(id),
            FOREIGN KEY (snapshot_description_id)
                REFERENCES snapshot_description(id),
            FOREIGN KEY (full_frame_description_id)
                REFERENCES full_frame_description(id)
        );
        """
    )
    conn.commit()
    conn.close()


def _to_iso(ts: datetime | str) -> str:
    if isinstance(ts, datetime):
        return ts.isoformat()
    return ts


def save_analysis(created_at: datetime, description: str) -> int:
    create_database()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO analysis (created_at, description) VALUES (?, ?);",
        (created_at.isoformat(), description),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def timestamp_from_description(description: str) -> str | None:
    create_database()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT created_at FROM analysis WHERE description = ? ORDER BY id LIMIT 1;",
        (description,),
    )
    row = cur.fetchone()
    conn.close()

    if row is None:
        return None
    return row[0]


def save_sequence_description_uniform(
    timestamp_start: datetime | str,
    timestamp_end: datetime | str,
    created_at: datetime | str,
    timestamps: list[datetime | str],
    llm_description: str,
    description_embedding: bytes | None = None,
    feedback: int = 0,
) -> int:
    create_database()
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
        (
            _to_iso(timestamp_start),
            _to_iso(timestamp_end),
            _to_iso(created_at),
            timestamps_json,
            llm_description,
            description_embedding,
            feedback,
        ),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def save_sequence_description_varied(
    timestamp_start: datetime | str,
    timestamp_end: datetime | str,
    created_at: datetime | str,
    timestamps: list[datetime | str],
    llm_description: str,
    description_embedding: bytes | None = None,
    feedback: int = 0,
) -> int:
    create_database()
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
        (
            _to_iso(timestamp_start),
            _to_iso(timestamp_end),
            _to_iso(created_at),
            timestamps_json,
            llm_description,
            description_embedding,
            feedback,
        ),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def save_snapshot_description(
    timestamp: datetime | str,
    created_at: datetime | str,
    llm_description: str,
    description_embedding: bytes | None = None,
    feedback: int = 0,
) -> int:
    create_database()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO snapshot_description (
            timestamp, created_at, llm_description, description_embedding, feedback
        ) VALUES (?, ?, ?, ?, ?);
        """,
        (_to_iso(timestamp), _to_iso(created_at), llm_description, description_embedding, feedback),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def save_full_frame_description(
    timestamp: datetime | str,
    created_at: datetime | str,
    llm_description: str,
    description_embedding: bytes | None = None,
    feedback: int = 0,
) -> int:
    create_database()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO full_frame_description (
            timestamp, created_at, llm_description, description_embedding, feedback
        ) VALUES (?, ?, ?, ?, ?);
        """,
        (_to_iso(timestamp), _to_iso(created_at), llm_description, description_embedding, feedback),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def save_description_group(
    timestamp_start: datetime | str,
    timestamp_end: datetime | str,
    sequence_description_uniform_id: int | None = None,
    sequence_description_varied_id: int | None = None,
    snapshot_description_id: int | None = None,
    full_frame_description_id: int | None = None,
) -> int:
    create_database()

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
            _to_iso(timestamp_start),
            _to_iso(timestamp_end),
            sequence_description_uniform_id,
            sequence_description_varied_id,
            snapshot_description_id,
            full_frame_description_id,
        ),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


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
    full_frame_timestamp: datetime | str | None = None
) -> dict[str, int]:
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
        description_embedding=normalize_text(uniform_llm_description),
    )
    varied_id = save_sequence_description_varied(
        timestamp_start=start_iso,
        timestamp_end=end_iso,
        created_at=created_at,
        timestamps=varied_timestamps,
        llm_description=varied_llm_description,
        description_embedding=normalize_text(varied_llm_description),
    )
    snapshot_id = save_snapshot_description(
        timestamp=snapshot_timestamp,
        created_at=created_at,
        llm_description=snapshot_llm_description,
        description_embedding=normalize_text(snapshot_llm_description),
    )
    full_frame_id = save_full_frame_description(
        timestamp=full_frame_timestamp,
        created_at=created_at,
        llm_description=full_frame_llm_description,
        description_embedding=normalize_text(full_frame_llm_description),
    )
    group_id = save_description_group(
        timestamp_start=start_iso,
        timestamp_end=end_iso,
        sequence_description_uniform_id=uniform_id,
        sequence_description_varied_id=varied_id,
        snapshot_description_id=snapshot_id,
        full_frame_description_id=full_frame_id,
    )

    return {
        "sequence_description_uniform_id": uniform_id,
        "sequence_description_varied_id": varied_id,
        "snapshot_description_id": snapshot_id,
        "full_frame_description_id": full_frame_id,
        "description_group_id": group_id,
    }


def image_from_timestamp(t, clip=10):
    # Söker igenom alla videofiler och kollar på filnamnen. Om filens namn visar att den innehåller det timestamps som söks, så öppna den filen, 
    # ta ut den framen som söks efter och konvertera den till bas64. 
    local_t = t.astimezone(RECORDINGS_TZ) if t.tzinfo is not None else t.replace(tzinfo=RECORDINGS_TZ)

    if not os.path.isdir(RECORDINGS_DIR):
        message = (
            f"Ingen matchande video: recordings directory does not exist "
            f"(dir={RECORDINGS_DIR}, timestamp={local_t.isoformat()})"
        )
        print(f"[database] {message}")
        raise FileNotFoundError(message)

    filenames = sorted(os.listdir(RECORDINGS_DIR))
    for f in filenames:
        try:
            s = datetime.strptime(f, "D%Y-%m-%d-T%H-%M-%S.mp4").replace(tzinfo=RECORDINGS_TZ)
            if s <= local_t < s + timedelta(seconds=clip):
                p = os.path.join(RECORDINGS_DIR, f)
                cap = cv2.VideoCapture(p)
                cap.set(cv2.CAP_PROP_POS_FRAMES, int((local_t - s).total_seconds() * cap.get(cv2.CAP_PROP_FPS)))
                ok, frame = cap.read()
                cap.release()
                if not ok:
                    raise RuntimeError("Kunde inte läsa frame")

                _, buffer = cv2.imencode(".jpg", frame)
                return base64.b64encode(buffer).decode("utf-8")
        except ValueError:
            continue

    sample_files = ", ".join(filenames[:5]) if filenames else "no files found"
    message = (
        f"Ingen matchande video for timestamp {local_t.isoformat()} in {RECORDINGS_DIR}. "
        f"Checked {len(filenames)} file(s). Sample: {sample_files}"
    )
    print(f"[database] {message}")
    raise FileNotFoundError(message)

def normalize_text(text: str) -> str:
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def tokenize(text: str):
    return text.split()

def char_ngrams(text: str, n: int = 3):
    text = normalize_text(text)
    compact = text.replace(" ", "_")
    if len(compact) < n:
        return [compact] if compact else []
    return [compact[i:i+n] for i in range(len(compact) - n + 1)]

def cosine_similarity(counter_a: Counter, counter_b: Counter) -> float:
    if not counter_a or not counter_b:
        return 0.0

    dot = sum(counter_a[k] * counter_b.get(k, 0) for k in counter_a)
    norm_a = math.sqrt(sum(v * v for v in counter_a.values()))
    norm_b = math.sqrt(sum(v * v for v in counter_b.values()))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot / (norm_a * norm_b)


def jaccard_similarity(set_a: set, set_b: set) -> float:
    if not set_a or not set_b:
        return 0.0
    inter = len(set_a & set_b)
    union = len(set_a | set_b)
    if union == 0:
        return 0.0
    return inter / union

def score(norm_query, query_tokens, query_token_set, query_trigrams, norm_desc: str) -> float:
    if not norm_query or not norm_desc:
        return 0.0

    desc_tokens = tokenize(norm_desc)
    desc_token_set = set(desc_tokens)

    # Tar snittet på antalet gemensama ord. query_token_set = {"server", "problem"}
    #desc_token_set = {"server", "startade", "om"} 
    # 1 gemensamt ord, 4 olika ord, 1/4 = 0.25
    token_jaccard = jaccard_similarity(query_token_set, desc_token_set)
    
    # Ger poäng på ord som är lika stavade
    desc_trigrams = Counter(char_ngrams(norm_desc, 3))
    trigram_cos = cosine_similarity(query_trigrams, desc_trigrams)
    
    # Ger extra poäng ifall hela söktexten finns i description
    substring_bonus = 0.25 if norm_query in norm_desc else 0.0

    # Ge extra poäng om query tokens är prefix till ord i description. Serv get poäng om server finns
    prefix_bonus = 0.0
    for qtok in query_tokens:
        if any(dtok.startswith(qtok) for dtok in desc_tokens):
            prefix_bonus += 0.05

    exact_token_bonus = 0.0
    # Ge extra poäng ifall ord finns i både query och description
    common_tokens = query_token_set & desc_token_set
    if common_tokens:
        exact_token_bonus = min(0.2, 0.05 * len(common_tokens))

    return (
        0.45 * trigram_cos +
        0.35 * token_jaccard +
        substring_bonus +
        prefix_bonus +
        exact_token_bonus
    )

if __name__ == "__main__":
    uvicorn.run("database:app", reload=True)
