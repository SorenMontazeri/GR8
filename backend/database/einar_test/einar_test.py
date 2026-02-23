from dbm import sqlite3
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

people = {"einar": 45, "alice": 7}

def create_database():
    # 1) connect (creates the file if it doesn't exist)
    conn = sqlite3.connect("mydb.sqlite")

    # 2) (recommended) ensure foreign keys are enforced in SQLite
    conn.execute("PRAGMA foreign_keys = ON;")

    # 3) run your SQL
    conn.executescript("""
    CREATE TABLE images (
        id       INTEGER PRIMARY KEY,
        jpg      BLOB NOT NULL
    );

    CREATE TABLE image_keywords (
        image_id INTEGER NOT NULL,
        keyword  TEXT NOT NULL,
        FOREIGN KEY (image_id) REFERENCES images(id)
    );
                       
    CREATE INDEX idx_image_keywords_keyword ON image_keywords(keyword);
    CREATE INDEX idx_image_keywords_image   ON image_keywords(image_id);""")

    # 4) save + close
    conn.commit()
    conn.close()

from pathlib import Path
import sqlite3

DB_PATH = Path(__file__).with_name("mydb.sqlite")


def add_image_with_keywords(image_filename: str, keywords: list[str]) -> int:
    image_path = Path(__file__).with_name(image_filename)

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        cur = conn.cursor()

        # 1) read image bytes
        jpg_bytes = image_path.read_bytes()

        # 2) insert image
        cur.execute("INSERT INTO images (jpg) VALUES (?);", (jpg_bytes,))
        image_id = cur.lastrowid

        # 3) insert keywords
        cur.executemany("INSERT INTO image_keywords (image_id, keyword) VALUES (?, ?);", [(image_id, kw.lower().strip()) for kw in keywords])

        conn.commit()
        return image_id


@app.get("/api/number/{name}")
def get_number(name: str):
    key = name.lower()
    if key not in people:
        raise HTTPException(status_code=404, detail="Name not found")
    return {"number": people[key]}  # <-- bara svaret


def save_analysis(timestamp, description):

def save_video(timestamp_start, timestamp_end, video_data):