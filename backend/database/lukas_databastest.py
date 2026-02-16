import sqlite3
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

def runData():
    conn = sqlite3.connect("test.db")
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON;")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS test (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
    );
    """)
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

@app.get("/api/info/{id}")
def get_info(id: int):
    conn = sqlite3.connect("test.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT ID, name FROM test WHERE id = ? ", (id,))
    row = cur.fetchone()
    conn.close
    return row


def get_number(name: str):
    key = name.lower()
    if key not in people:
        raise HTTPException(status_code=404, detail="Name not found")
    return {"number": people[key]}  # <-- bara svaret
