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

if __name__ == "__main__":
    uvicorn.run("database:app", reload=True)
