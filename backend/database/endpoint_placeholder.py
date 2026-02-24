import sqlite3

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import base64
from pathlib import Path

DB_PATH = Path(__file__).with_name("test.db")


def runData():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON;")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS test (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
    );
    """)
    cur.execute("SELECT COUNT(*) FROM test;")
    row_count = cur.fetchone()[0]
    if row_count == 0:
        testlist = ["Lukas", "Lisa", "Einar", "Cora"]
        cur.executemany("INSERT INTO test (name) VALUES (?);", [(name,) for name in testlist])

    conn.commit()
    conn.close()



app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_seed() -> None:
    runData()


@app.get("/api/info/{id}")
def get_info(id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT ID, name FROM test WHERE id = ? ", (id,))
    row = cur.fetchone()
    conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="id not found")
    return {"id": row["id"], "name": row["name"]}

@app.get("/api/image/{name}")
def get_image(name: str):
    if name in ["lisa", "einar", "cora"]:
        image_path = Path(__file__).with_name(f"{name}.jpg")
        image_bytes = image_path.read_bytes()
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        return {
            "name": name,
            "image": image_b64,
        }
    else:
        raise HTTPException(status_code=404, detail="Image not found")
