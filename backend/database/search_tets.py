import json
import sqlite3
from sentence_transformers import SentenceTransformer

DB_PATH = "events.db"
MODEL_PATH = "./models/all-MiniLM-L6-v2"


conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
from pathlib import Path
from sentence_transformers import SentenceTransformer

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_DIR = "./models/all-MiniLM-L6-v2"

if Path(MODEL_DIR).exists():
    model = SentenceTransformer(MODEL_DIR)
else:
    model = SentenceTransformer(MODEL_NAME)
    model.save(MODEL_DIR)


def init_db():
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            description TEXT NOT NULL,
            embedding TEXT NOT NULL
        )
    """)
    conn.commit()


def embed(text: str):
    return model.encode(text, normalize_embeddings=True).tolist()


def add_event(timestamp: str, description: str):
    embedding = json.dumps(embed(description))
    conn.execute(
        "INSERT INTO events (timestamp, description, embedding) VALUES (?, ?, ?)",
        (timestamp, description, embedding),
    )
    conn.commit()


def cosine_similarity(a, b):
    return sum(x * y for x, y in zip(a, b))


def search(query: str, limit: int = 5):
    query_embedding = embed(query)

    rows = conn.execute(
        "SELECT timestamp, description, embedding FROM events"
    ).fetchall()

    results = []
    for row in rows:
        desc_embedding = json.loads(row["embedding"])
        score = cosine_similarity(query_embedding, desc_embedding)

        results.append({
            "timestamp": row["timestamp"],
            "description": row["description"],
            "score": round(score, 4),
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


if __name__ == "__main__":
    init_db()

    
    results = search("Övervakningssystemet byggde inte om index efter inkonsistenta resultat på nod A")
    for r in results:
       print(r["timestamp"], "-", r["description"], "-", r["score"])

    conn.close()