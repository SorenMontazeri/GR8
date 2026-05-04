from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import base64
import csv
import json
import os
import shutil

from pathlib import Path
from sentence_transformers import SentenceTransformer

try:
    from database import settings_editor
except ImportError:
    import settings_editor

import sqlite3

import cv2
import uvicorn
from zoneinfo import ZoneInfo

DB_PATH = Path(__file__).with_name("analysis.sqlite")
SETTINGS_PATH = Path(__file__).with_name("settings.json")
settings_editor.SETTINGS_PATH = SETTINGS_PATH
BACKEND_DIR = Path(__file__).resolve().parent.parent
CAMERA_ID = "1"
RECORDINGS_DIR = BACKEND_DIR / "recordings" / CAMERA_ID
INDEX_PATH = BACKEND_DIR / "indexes" / f"index-{CAMERA_ID}.csv"

RECORDINGS_TZ = ZoneInfo("Europe/Stockholm")
MODEL_PATH = "./models/all-MiniLM-L6-v2"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_DIR = "./models/all-MiniLM-L6-v2"
model = None
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FEEDBACK_TARGETS = {
    "uniform": ("sequence_description_uniform", "sequence_description_uniform_id"),
    "varied": ("sequence_description_varied", "sequence_description_varied_id"),
    "snapshot": ("snapshot_description", "snapshot_description_id"),
    "fullframe": ("full_frame_description", "full_frame_description_id"),
    "fullframe": ("full_frame_description", "full_frame_description_id"),
    "full_frame": ("full_frame_description", "full_frame_description_id"),
}
FEEDBACK_MIN = 0
FEEDBACK_MAX = 5


class FeedbackRequest(BaseModel):
    description_type: str
    id: int  # description_group.id
    feedback: int  # integer rating in range 0..5


class SettingsRequest(BaseModel):
    min_event_duration: int = 0
    prompt_fullframe_snapshot: str = ""
    prompt_uniform_movement: str = ""
    fullframe_time: int = -1
    uniform_samplerate: int = 1
    uniform_samplerate_value: int = 0
    movement_tracker_type: int = 1
    movement_tracker_type_threshhold: int = 1
    movement_samplerate: int = 1
    movement_samplerate_value: int = 0


@app.get("/api/settings")
def get_settings():
    return load_settings()


@app.post("/api/settings")
def post_settings(payload: SettingsRequest):
    settings = payload.model_dump()
    validate_settings(settings)
    save_settings(settings)
    return settings


@app.get("/api/event/{query}")
def get_events(query: str):
    best_event = find_best_event(query)
    if best_event is None:
        raise HTTPException(status_code=404, detail=f"No events found for query '{query}'")

    create_database()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            dg.id AS dg_id,
            dg.timestamp_start AS dg_timestamp_start,
            dg.timestamp_end AS dg_timestamp_end,
            dg.sequence_description_uniform_id AS dg_uniform_id,
            dg.sequence_description_varied_id AS dg_varied_id,
            dg.snapshot_description_id AS dg_snapshot_id,
            dg.full_frame_description_id AS dg_full_frame_id,

            u.id AS u_id,
            u.timestamp_start AS u_timestamp_start,
            u.timestamp_end AS u_timestamp_end,
            u.created_at AS u_created_at,
            u.timestamps_json AS u_timestamps_json,
            u.images_base64_json AS u_images_base64_json,
            u.llm_description AS u_llm_description,
            u.description_embedding AS u_description_embedding,
            u.number_of_tokens AS u_number_of_tokens,
            u.feedback AS u_feedback,

            v.id AS v_id,
            v.timestamp_start AS v_timestamp_start,
            v.timestamp_end AS v_timestamp_end,
            v.created_at AS v_created_at,
            v.timestamps_json AS v_timestamps_json,
            v.images_base64_json AS v_images_base64_json,
            v.llm_description AS v_llm_description,
            v.description_embedding AS v_description_embedding,
            v.number_of_tokens AS v_number_of_tokens,
            v.feedback AS v_feedback,

            s.id AS s_id,
            s.timestamp AS s_timestamp,
            s.snapshot_image_base64 AS s_snapshot_image_base64,
            s.created_at AS s_created_at,
            s.llm_description AS s_llm_description,
            s.description_embedding AS s_description_embedding,
            s.number_of_tokens AS s_number_of_tokens,
            s.feedback AS s_feedback,

            f.id AS f_id,
            f.timestamp AS f_timestamp,
            f.image_base64 AS f_image_base64,
            f.created_at AS f_created_at,
            f.llm_description AS f_llm_description,
            f.description_embedding AS f_description_embedding,
            f.number_of_tokens AS f_number_of_tokens,
            f.feedback AS f_feedback
        FROM description_group dg
        LEFT JOIN sequence_description_uniform u ON u.id = dg.sequence_description_uniform_id
        LEFT JOIN sequence_description_varied v ON v.id = dg.sequence_description_varied_id
        LEFT JOIN snapshot_description s ON s.id = dg.snapshot_description_id
        LEFT JOIN full_frame_description f ON f.id = dg.full_frame_description_id
        WHERE dg.id = ?;
        """,
        (best_event["group_id"],),
    )
    row = cur.fetchone()
    conn.close()

    if row is None:
        raise HTTPException(status_code=404, detail=f"No description_group found with id={best_event['group_id']}")

    uniform_timestamps = _parse_json(row["u_timestamps_json"]) if row["u_timestamps_json"] else []
    varied_timestamps = _parse_json(row["v_timestamps_json"]) if row["v_timestamps_json"] else []
    uniform_images = _parse_json(row["u_images_base64_json"]) if row["u_images_base64_json"] else None
    varied_images = _parse_json(row["v_images_base64_json"]) if row["v_images_base64_json"] else None
    if not isinstance(uniform_images, list):
        uniform_images = _images_from_timestamps(uniform_timestamps)
    if not isinstance(varied_images, list):
        varied_images = _images_from_timestamps(varied_timestamps)
    if row["s_snapshot_image_base64"] is not None:
        snapshot_image = row["s_snapshot_image_base64"]
    else:
        snapshot_image = _safe_image_from_iso(row["s_timestamp"]) if row["s_timestamp"] is not None else None
    if row["f_image_base64"] is not None:
        full_frame_image = row["f_image_base64"]
    else:
        full_frame_image = _safe_image_from_iso(row["f_timestamp"]) if row["f_timestamp"] is not None else None

    return {
        "query": query,
        "match": best_event,
        "description_group": {
            "id": row["dg_id"],
            "timestamp_start": row["dg_timestamp_start"],
            "timestamp_end": row["dg_timestamp_end"],
            "sequence_description_uniform_id": row["dg_uniform_id"],
            "sequence_description_varied_id": row["dg_varied_id"],
            "snapshot_description_id": row["dg_snapshot_id"],
            "full_frame_description_id": row["dg_full_frame_id"],
        },
        "uniform": {
            "id": row["u_id"],
            "timestamp_start": row["u_timestamp_start"],
            "timestamp_end": row["u_timestamp_end"],
            "created_at": row["u_created_at"],
            "timestamps_json": uniform_timestamps,
            "images": uniform_images,
            "llm_description": row["u_llm_description"],
            "description_embedding": _parse_json(row["u_description_embedding"]),
            "number_of_tokens": row["u_number_of_tokens"],
            "feedback": row["u_feedback"],
        } if row["u_id"] is not None else None,
        "varied": {
            "id": row["v_id"],
            "timestamp_start": row["v_timestamp_start"],
            "timestamp_end": row["v_timestamp_end"],
            "created_at": row["v_created_at"],
            "timestamps_json": varied_timestamps,
            "images": varied_images,
            "llm_description": row["v_llm_description"],
            "description_embedding": _parse_json(row["v_description_embedding"]),
            "number_of_tokens": row["v_number_of_tokens"],
            "feedback": row["v_feedback"],
        } if row["v_id"] is not None else None,
        "snapshot": {
            "id": row["s_id"],
            "timestamp": row["s_timestamp"],
            "image": snapshot_image,
            "created_at": row["s_created_at"],
            "llm_description": row["s_llm_description"],
            "description_embedding": _parse_json(row["s_description_embedding"]),
            "number_of_tokens": row["s_number_of_tokens"],
            "feedback": row["s_feedback"],
        } if row["s_id"] is not None else None,
        "full_frame": {
            "id": row["f_id"],
            "timestamp": row["f_timestamp"],
            "image": full_frame_image,
            "created_at": row["f_created_at"],
            "llm_description": row["f_llm_description"],
            "description_embedding": _parse_json(row["f_description_embedding"]),
            "number_of_tokens": row["f_number_of_tokens"],
            "feedback": row["f_feedback"],
        } if row["f_id"] is not None else None,
    }

# lisa cora 
@app.get("/api/stats")
def get_stats():
    create_database()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    current_settings = settings_editor.normalized_settings_json(load_settings())

    stats = {}

    mapping = {
        "snapshot": ("snapshot_description", "snapshot_description_id"),
        "fullframe": ("full_frame_description", "full_frame_description_id"),
        "uniform": ("sequence_description_uniform", "sequence_description_uniform_id"),
        "varied": ("sequence_description_varied", "sequence_description_varied_id"),
    }

    for key, (table, fk_col) in mapping.items():
        cur.execute(
            f"""
            SELECT COALESCE(SUM(t.feedback), 0)
            FROM description_group dg
            JOIN {table} t ON t.id = dg.{fk_col}
            WHERE dg.settings_json = ?;
            """,
            (current_settings,),
        )
        stats[key] = cur.fetchone()[0]

    conn.close()
    return stats

@app.post("/api/feedback", status_code=204)
def post_feedback(payload: FeedbackRequest):
    update_feedback(payload.description_type, payload.id, payload.feedback)


@app.get("/api/stats")
def get_stats():
    create_database()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Här använder vi de nya namnen uniform/varied
    stats = {}
    mapping = {
        "snapshot": "snapshot_description",
        "fullframe": "full_frame_description",
        "uniform": "sequence_description_uniform",
        "varied": "sequence_description_varied",
    }

    for key, table in mapping.items():
        cur.execute(f"SELECT SUM(feedback) FROM {table}")
        res = cur.fetchone()
        stats[key] = res if res and res is not None else 0

    conn.close()
    return stats


@app.post("/api/admin/reset")
@app.patch("/api/admin/reset")
def reset_storage():
    """Endpoint som anropas från frontend för att rensa allt."""
    deleted_database_file = clear_database_file()
    deleted_recordings = clear_recordings_directory()
    return {
        "status": "ok",
        "deleted_database_file": deleted_database_file,
        "deleted_recordings": deleted_recordings,
    }


def clear_database_file() -> bool:
    """Tar bort sqlite-filen."""
    if DB_PATH.exists():
        DB_PATH.unlink()
        return True
    return False


def clear_recordings_directory() -> int:
    """Rensar mappen med inspelningar/bilder."""
    import shutil

    recordings_path = Path(RECORDINGS_DIR)
    if not recordings_path.exists() or not recordings_path.is_dir():
        return 0

    deleted_file_count = 0
    for child in recordings_path.iterdir():
        if child.is_file() or child.is_symlink():
            child.unlink()
            deleted_file_count += 1
        elif child.is_dir():
            deleted_file_count += sum(1 for path in child.rglob("*") if path.is_file())
            shutil.rmtree(child)
    return deleted_file_count


def update_feedback(description_type: str, group_id: int, feedback_value: int) -> None:
    try:
        _validate_feedback_range(feedback_value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"feedback must be an integer between {FEEDBACK_MIN} and {FEEDBACK_MAX}",
        ) from exc

    target = FEEDBACK_TARGETS.get(description_type.strip().lower())
    if target is None:
        raise HTTPException(
            status_code=400,
            detail="description_type must be one of: uniform, varied, snapshot, full_frame",
        )
    table, group_fk_column = target

    create_database()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        f"SELECT {group_fk_column} FROM description_group WHERE id = ?;",
        (group_id,),
    )
    row = cur.fetchone()
    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail=f"No description_group found with id={group_id}")

    target_row_id = row[0]
    if target_row_id is None:
        conn.close()
        raise HTTPException(
            status_code=404,
            detail=f"description_group id={group_id} has no linked {description_type} row",
        )

    cur.execute(f"UPDATE {table} SET feedback = ? WHERE id = ?;", (feedback_value, target_row_id))
    updated = cur.rowcount
    conn.commit()
    conn.close()

    if updated == 0:
        raise HTTPException(status_code=404, detail=f"No row found with id={target_row_id} in {table}")


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
            images_base64_json TEXT,
            llm_description TEXT NOT NULL,
            description_embedding TEXT,
            number_of_tokens INTEGER,
            feedback INTEGER NOT NULL DEFAULT 0 CHECK (feedback BETWEEN 0 AND 5)
        );

        CREATE TABLE IF NOT EXISTS sequence_description_varied (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp_start TEXT NOT NULL,
            timestamp_end TEXT NOT NULL,
            created_at TEXT NOT NULL,
            timestamps_json TEXT NOT NULL,
            images_base64_json TEXT,
            llm_description TEXT NOT NULL,
            description_embedding TEXT,
            number_of_tokens INTEGER,
            feedback INTEGER NOT NULL DEFAULT 0 CHECK (feedback BETWEEN 0 AND 5)
        );

        CREATE TABLE IF NOT EXISTS snapshot_description (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            snapshot_image_base64 TEXT,
            created_at TEXT NOT NULL,
            llm_description TEXT NOT NULL,
            description_embedding TEXT,
            number_of_tokens INTEGER,
            feedback INTEGER NOT NULL DEFAULT 0 CHECK (feedback BETWEEN 0 AND 5)
        );

        CREATE TABLE IF NOT EXISTS full_frame_description (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            image_base64 TEXT,
            created_at TEXT NOT NULL,
            llm_description TEXT NOT NULL,
            description_embedding TEXT,
            number_of_tokens INTEGER,
            feedback INTEGER NOT NULL DEFAULT 0 CHECK (feedback BETWEEN 0 AND 5)
        );

        CREATE TABLE IF NOT EXISTS description_group (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp_start TEXT NOT NULL,
            timestamp_end TEXT NOT NULL,
            sequence_description_uniform_id INTEGER,
            sequence_description_varied_id INTEGER,
            snapshot_description_id INTEGER,
            full_frame_description_id INTEGER,
            settings_json TEXT,
            FOREIGN KEY (sequence_description_uniform_id)
                REFERENCES sequence_description_uniform(id),
            FOREIGN KEY (sequence_description_varied_id)
                REFERENCES sequence_description_varied(id),
            FOREIGN KEY (snapshot_description_id)
                REFERENCES snapshot_description(id),
            FOREIGN KEY (full_frame_description_id)
                REFERENCES full_frame_description(id)
        );

        CREATE TABLE IF NOT EXISTS app_settings (
            id INTEGER PRIMARY KEY,
            settings_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )

    migrations = [
        ("snapshot_description", "snapshot_image_base64", "TEXT"),
        ("sequence_description_uniform", "images_base64_json", "TEXT"),
        ("sequence_description_varied", "images_base64_json", "TEXT"),
        ("full_frame_description", "image_base64", "TEXT"),
        ("sequence_description_uniform", "number_of_tokens", "INTEGER"),
        ("sequence_description_varied", "number_of_tokens", "INTEGER"),
        ("snapshot_description", "number_of_tokens", "INTEGER"),
        ("full_frame_description", "number_of_tokens", "INTEGER"),
        ("description_group", "settings_json", "TEXT"),
    ]
    for table, column, column_type in migrations:
        try:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type};")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
    default_settings_json = settings_editor.normalized_settings_json(settings_editor.load_settings())
    cur.execute(
        "UPDATE description_group SET settings_json = ? WHERE settings_json IS NULL;",
        (default_settings_json,),
    )
    conn.commit()
    conn.close()


def default_settings() -> dict:
    return settings_editor.default_settings()


def validate_settings(settings: dict) -> None:
    if settings["min_event_duration"] < 0:
        raise HTTPException(status_code=400, detail="min_event_duration must be >= 0")
    if settings["fullframe_time"] not in {-1, 0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100}:
        raise HTTPException(status_code=400, detail="fullframe_time must be -1 or 0-100 in steps of 10")
    if settings["uniform_samplerate"] not in {1, 2, 3}:
        raise HTTPException(status_code=400, detail="uniform_samplerate must be 1, 2, or 3")
    if settings["movement_samplerate"] not in {1, 2, 3}:
        raise HTTPException(status_code=400, detail="movement_samplerate must be 1, 2, or 3")
    if settings["movement_tracker_type"] not in {1, 2}:
        raise HTTPException(status_code=400, detail="movement_tracker_type must be 1 or 2")
    if settings["uniform_samplerate_value"] < 0:
        raise HTTPException(status_code=400, detail="uniform_samplerate_value must be >= 0")
    if settings["movement_samplerate_value"] < 0:
        raise HTTPException(status_code=400, detail="movement_samplerate_value must be >= 0")
    if settings["movement_tracker_type_threshhold"] < 0:
        raise HTTPException(status_code=400, detail="movement_tracker_type_threshhold must be >= 0")


def save_settings(settings: dict) -> None:
    settings_editor.save_settings(settings)
    create_database()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO app_settings (id, settings_json, updated_at)
        VALUES (1, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            settings_json = excluded.settings_json,
            updated_at = excluded.updated_at;
        """,
        (json.dumps(settings), datetime.now(RECORDINGS_TZ).isoformat()),
    )
    conn.commit()
    conn.close()


def load_settings() -> dict:
    file_settings = settings_editor.load_settings()
    if file_settings:
        settings = default_settings()
        settings.update(file_settings)
        return settings

    create_database()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT settings_json FROM app_settings WHERE id = 1;")
    row = cur.fetchone()
    conn.close()

    if row is None:
        return default_settings()

    settings = default_settings()
    settings.update(json.loads(row[0]))
    return settings


def _to_iso(ts: datetime | str) -> str:
    if isinstance(ts, datetime):
        return ts.isoformat()
    return ts


def _validate_feedback_range(feedback_value: int) -> None:
    if feedback_value < FEEDBACK_MIN or feedback_value > FEEDBACK_MAX:
        raise ValueError(f"feedback must be between {FEEDBACK_MIN} and {FEEDBACK_MAX}")


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


def save_sequence_description_uniform(
    timestamp_start: datetime | str,
    timestamp_end: datetime | str,
    created_at: datetime | str,
    timestamps: list[datetime | str],
    llm_description: str,
    images_base64: list[str] | None = None,
    description_embedding: str | None = None,
    number_of_tokens: int | None = None,
    feedback: int = 0,
) -> int:
    _validate_feedback_range(feedback)
    create_database()
    timestamps_json = json.dumps([_to_iso(ts) for ts in timestamps])
    images_base64_json = json.dumps(images_base64) if images_base64 is not None else None

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO sequence_description_uniform (
            timestamp_start, timestamp_end, created_at, timestamps_json,
            images_base64_json, llm_description, description_embedding, number_of_tokens, feedback
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            _to_iso(timestamp_start),
            _to_iso(timestamp_end),
            _to_iso(created_at),
            timestamps_json,
            images_base64_json,
            llm_description,
            description_embedding,
            number_of_tokens,
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
    images_base64: list[str] | None = None,
    description_embedding: str | None = None,
    number_of_tokens: int | None = None,
    feedback: int = 0,
) -> int:
    _validate_feedback_range(feedback)
    create_database()
    timestamps_json = json.dumps([_to_iso(ts) for ts in timestamps])
    images_base64_json = json.dumps(images_base64) if images_base64 is not None else None

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO sequence_description_varied (
            timestamp_start, timestamp_end, created_at, timestamps_json,
            images_base64_json, llm_description, description_embedding, number_of_tokens, feedback
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            _to_iso(timestamp_start),
            _to_iso(timestamp_end),
            _to_iso(created_at),
            timestamps_json,
            images_base64_json,
            llm_description,
            description_embedding,
            number_of_tokens,
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
    snapshot_image_base64: str | None = None,
    description_embedding: str | None = None,
    number_of_tokens: int | None = None,
    feedback: int = 0,
) -> int:
    _validate_feedback_range(feedback)
    create_database()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO snapshot_description (
            timestamp, snapshot_image_base64, created_at, llm_description,
            description_embedding, number_of_tokens, feedback
        ) VALUES (?, ?, ?, ?, ?, ?, ?);
        """,
        (
            _to_iso(timestamp),
            snapshot_image_base64,
            _to_iso(created_at),
            llm_description,
            description_embedding,
            number_of_tokens,
            feedback,
        ),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def save_full_frame_description(
    timestamp: datetime | str,
    created_at: datetime | str,
    llm_description: str,
    image_base64: str | None = None,
    description_embedding: str | None = None,
    number_of_tokens: int | None = None,
    feedback: int = 0,
) -> int:
    _validate_feedback_range(feedback)
    create_database()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO full_frame_description (
            timestamp, image_base64, created_at, llm_description,
            description_embedding, number_of_tokens, feedback
        ) VALUES (?, ?, ?, ?, ?, ?, ?);
        """,
        (_to_iso(timestamp), image_base64, _to_iso(created_at), llm_description, description_embedding, feedback),
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
    settings: dict | None = None,
) -> int:
    create_database()
    if settings is None:
        settings = load_settings()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO description_group (
            timestamp_start, timestamp_end,
            sequence_description_uniform_id, sequence_description_varied_id,
            snapshot_description_id, full_frame_description_id, settings_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?);
        """,
        (
            _to_iso(timestamp_start),
            _to_iso(timestamp_end),
            sequence_description_uniform_id,
            sequence_description_varied_id,
            snapshot_description_id,
            full_frame_description_id,
            settings_editor.normalized_settings_json(settings)
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
    full_frame_timestamp: datetime | str | None = None,
    snapshot_image_base64: str | None = None,
    full_frame_image_base64: str | None = None,
    uniform_images_base64: list[str] | None = None,
    varied_images_base64: list[str] | None = None,
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
        images_base64=uniform_images_base64,
        description_embedding=json.dumps(embed(uniform_llm_description)),
        number_of_tokens=uniform_number_of_tokens,
    )
    varied_id = save_sequence_description_varied(
        timestamp_start=start_iso,
        timestamp_end=end_iso,
        created_at=created_at,
        timestamps=varied_timestamps,
        llm_description=varied_llm_description,
        images_base64=varied_images_base64,
        description_embedding=json.dumps(embed(varied_llm_description)),
        number_of_tokens=varied_number_of_tokens,
    )
    snapshot_id = save_snapshot_description(
        timestamp=snapshot_timestamp,
        created_at=created_at,
        llm_description=snapshot_llm_description,
        snapshot_image_base64=snapshot_image_base64,
        description_embedding=json.dumps(embed(snapshot_llm_description)),
        number_of_tokens=snapshot_number_of_tokens,
    )
    full_frame_id = save_full_frame_description(
        timestamp=full_frame_timestamp,
        created_at=created_at,
        llm_description=full_frame_llm_description,
        image_base64=full_frame_image_base64,
        description_embedding=json.dumps(embed(full_frame_llm_description)),
        number_of_tokens=full_frame_number_of_tokens,
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
    local_t = t.astimezone(RECORDINGS_TZ) if t.tzinfo is not None else t.replace(tzinfo=RECORDINGS_TZ)

    if not INDEX_PATH.exists():
        message = (
            f"Ingen matchande video: index file does not exist "
            f"(index={INDEX_PATH}, timestamp={local_t.isoformat()})"
        )
        print(f"[database] {message}")
        raise FileNotFoundError(message)

    with INDEX_PATH.open(newline="") as index_file:
        rows = list(csv.DictReader(index_file))

    for row in rows:
        start = datetime.fromisoformat(row["segment_start_camera_time"])
        end = datetime.fromisoformat(row["segment_end_camera_time"])
        if start <= local_t <= end:
            video_path = Path(row["file_name"])
            if not video_path.is_absolute():
                video_path = RECORDINGS_DIR / video_path
            cap = cv2.VideoCapture(str(video_path))
            cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, (local_t - start).total_seconds()) * 1000.0)
            ok, frame = cap.read()
            cap.release()
            if not ok:
                raise RuntimeError("Kunde inte läsa frame")

            _, buffer = cv2.imencode(".jpg", frame)
            return base64.b64encode(buffer).decode("utf-8")

    message = (
        f"Ingen matchande video for timestamp {local_t.isoformat()} in {INDEX_PATH}. "
        f"Checked {len(rows)} index row(s)."
    )
    print(f"[database] {message}")
    raise FileNotFoundError(message)

def get_model():
    global model
    if model is None:
        if Path(MODEL_DIR).exists():
            model = SentenceTransformer(MODEL_DIR)
        else:
            model = SentenceTransformer(MODEL_NAME)
            model.save(MODEL_DIR)
    return model

def embed(text: str):
    embed_model = get_model()
    return embed_model.encode(text, normalize_embeddings=True).tolist()

def cosine_similarity(a, b):
    return sum(x * y for x, y in zip(a, b))

def _parse_json(value):
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


def _safe_image_from_iso(timestamp_value):
    if timestamp_value is None:
        return None
    ts_text = timestamp_value if isinstance(timestamp_value, str) else _to_iso(timestamp_value)
    try:
        return image_from_timestamp(datetime.fromisoformat(ts_text))
    except Exception:
        return None


def _images_from_timestamps(timestamps):
    if not isinstance(timestamps, list):
        return []
    images = []
    for ts in timestamps:
        images.append(_safe_image_from_iso(ts))
    return images


def find_best_event(query):
    current_settings = settings_editor.normalized_settings_json(load_settings())
    query_embedding = embed(query)
    create_database()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    best_score = None
    best_group_id = None
    best_matched_row_id = None
    best_matched_type = None

    cur.execute(
        """
        SELECT
            dg.id AS group_id,
            dg.sequence_description_uniform_id AS uniform_id,
            dg.sequence_description_varied_id AS varied_id,
            dg.snapshot_description_id AS snapshot_id,
            dg.full_frame_description_id AS full_frame_id,
            u.description_embedding AS uniform_embedding,
            v.description_embedding AS varied_embedding,
            s.description_embedding AS snapshot_embedding,
            f.description_embedding AS full_frame_embedding
        FROM description_group dg
        LEFT JOIN sequence_description_uniform u ON u.id = dg.sequence_description_uniform_id
        LEFT JOIN sequence_description_varied v ON v.id = dg.sequence_description_varied_id
        LEFT JOIN snapshot_description s ON s.id = dg.snapshot_description_id
        LEFT JOIN full_frame_description f ON f.id = dg.full_frame_description_id
        WHERE dg.settings_json= ?
        """,
        (current_settings,)
    )

    rows = cur.fetchall()
    conn.close()
    for row in rows:
        candidates = [
            ("uniform", row["uniform_id"], row["uniform_embedding"]),
            ("varied", row["varied_id"], row["varied_embedding"]),
            ("snapshot", row["snapshot_id"], row["snapshot_embedding"]),
            ("full_frame", row["full_frame_id"], row["full_frame_embedding"]),
        ]

        for desc_type, desc_id, embedding_text in candidates:
            if desc_id is None or embedding_text is None:
                continue
            desc_embedding = _parse_json(embedding_text)
            if not isinstance(desc_embedding, list):
                continue

            score = cosine_similarity(query_embedding, desc_embedding)
            if best_score is None or score > best_score:
                best_score = score
                best_group_id = row["group_id"]
                best_matched_row_id = desc_id
                best_matched_type = desc_type

    if best_group_id is None:
        return None

    return {
        "group_id": best_group_id,
        "score": best_score,
        "matched_type": best_matched_type,
        "matched_row_id": best_matched_row_id,
    }


def seed_test_data():
    # Reference recording: recordings/1/D2026-02-09-T11-51-00.mp4
    base_video_time = datetime(2026, 2, 9, 11, 51, 0, tzinfo=RECORDINGS_TZ)
    event_start = base_video_time + timedelta(seconds=1)
    event_end = base_video_time + timedelta(seconds=6)
    snapshot_ts = base_video_time + timedelta(seconds=2)
    full_frame_ts = base_video_time + timedelta(seconds=3)

    snapshot_b64 = None
    try:
        snapshot_b64 = image_from_timestamp(snapshot_ts)
    except FileNotFoundError:
        snapshot_b64 = None

    save_description_bundle(
        timestamp_start=event_start,
        timestamp_end=event_end,
        created_at=base_video_time,
        uniform_llm_description="En person går genom rummet i jämn takt.",
        varied_llm_description="En person syns först vid dörren och rör sig sedan mot mitten av rummet3.",
        snapshot_llm_description="En person står nära dörröppningen.",
        full_frame_llm_description="Rummet är synligt i helbild med en person som passerar genom scenen.",
        uniform_timestamps=[event_start, event_end],
        varied_timestamps=[event_start, event_end],
        snapshot_timestamp=snapshot_ts,
        full_frame_timestamp=full_frame_ts,
        snapshot_image_base64=snapshot_b64,
    )

# lisa cora 

@app.post("/api/admin/reset")
@app.patch("/api/admin/reset")
def reset_storage():
    """Endpoint som anropas från frontend för att rensa allt."""
    deleted_database_file = clear_database_file()
    deleted_recordings = clear_recordings_directory()
    return {
        "status": "ok",
        "deleted_database_file": deleted_database_file,
        "deleted_recordings": deleted_recordings,
    }

def clear_database_file() -> bool:
    """Tar bort sqlite-filen."""
    if DB_PATH.exists():
        DB_PATH.unlink()
        return True
    return False

def clear_recordings_directory() -> int:
    """Rensar mappen med inspelningar/bilder."""
    import shutil
    recordings_path = Path(RECORDINGS_DIR)
    if not recordings_path.exists() or not recordings_path.is_dir():
        return 0

    deleted_file_count = 0
    for child in recordings_path.iterdir():
        if child.is_file() or child.is_symlink():
            child.unlink()
            deleted_file_count += 1
        elif child.is_dir():
            deleted_file_count += sum(1 for path in child.rglob("*") if path.is_file())
            shutil.rmtree(child)
    return deleted_file_count

if __name__ == "__main__":
    #seed_test_data()
    ##seed_test_data()
    uvicorn.run("database:app", host="127.0.0.1", port=8000, reload=False)
