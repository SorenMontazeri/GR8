from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import base64
from pathlib import Path
import sqlite3
from pathlib import Path
import os, cv2, base64
from datetime import datetime, timedelta

DB_PATH = Path(__file__).with_name("analysis.sqlite")
RECORDINGS_DIR = os.path.join(os.path.dirname(__file__), "recordings/1")
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
    if name == "bov":
        return {
            "name": name,
            "image": image_from_timestamp(timestamp_from_description(name)),
        }
    else:
        raise HTTPException(status_code=404, detail="Image not found")


def create_database() -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            description TEXT NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()


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


def image_from_timestamp(t, clip=10):
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