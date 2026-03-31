from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import base64
import uvicorn
from pathlib import Path
import sqlite3
from pathlib import Path
import os, cv2, base64
from datetime import datetime, timedelta
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


@app.get("/api/image/{name}")
def get_image(name: str):
    #Hämtar en bild från en request från frontend. Indata är en tagg/description som söks på, och det returnar en bas64 sträng med bilden
    ts = timestamp_from_description(name)
    if ts is None:
        raise HTTPException(status_code=404, detail="No timestamp for this description")

    t = datetime.fromisoformat(ts)
    try:
        return {"name": name, "image": image_from_timestamp(t)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def create_database() -> None:
    # Här kommer vi in om databasen vi vill lägga in något i inte finns. Isåfall vill vi göra ett nytt table så vi kan lägga in datan.
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
    # Sammanfattningen som kommer från analysdelen kallar på den här funktionen och sparar allt i ett table med datetime och keywords.
    create_database()
    rows = [(created_at.isoformat(), d) for d in description]
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.executemany(
        "INSERT INTO analysis (created_at, description) VALUES (?, ?);",
        rows
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def timestamp_from_description(description: str) -> str | None:
    # Hjälpfunktion som är det som faktiskt hämtar ut vilken datetime som hör till den desctiption som söks efter.
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

                # Encode to JPEG in memory
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
