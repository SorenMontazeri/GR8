from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import base64
from pathlib import Path
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).with_name("analysis.sqlite")
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
        image_path = Path(__file__).with_name(f"output.jpg")
        image_bytes = image_path.read_bytes()
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        return {
            "name": name,
            "image": image_b64,
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


def get_timestamp_by_description(description: str) -> str | None:
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