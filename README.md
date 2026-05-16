# GR8

GR8 is a full-stack video analysis search tool. The backend receives camera event data, extracts relevant frames, asks a multimodal model for descriptions, stores those descriptions in SQLite, and makes them searchable with text embeddings. The frontend lets a user search for events, inspect matching frames and sequences, tune analysis settings, and rate the quality of the results.

## What the System Does

- Reads camera metadata over MQTT and video over RTSP.
- Maintains a short hot buffer of recent video frames.
- Matches event timestamps to full-frame images and event snapshots.
- Selects image sequences using both time-based and movement-based strategies.
- Sends selected images to an LLM analysis client.
- Stores descriptions, timestamps, image data, embeddings, settings, and feedback in SQLite.
- Lets users search using natural language from the frontend and returns the best matching event bundle.

## Repository Structure 
#TODO: Fill in comments for your files (what they do)

```
.
|-- start.py                     # Starts backend API and frontend dev server
|-- init.py                      # Sets up backend and frontend dependencies
|-- backend/
|   |-- database/
|   |   |-- database.py
|   |   |-- settings.json
|   |   `-- settings_editor.py  
|   |-- ingestion/
|   |   |-- camera.py            # Connects RTSP video and MQTT events to the ingestion pipeline
|   |   |-- analysis/            # Contains code that picks uniform and movement-based image sequences before sending them to LLM
|   |   |-- buffers/             # Ring buffers for recent RTSP frames and MQTT events
|   |   |-- normalization/       # Maps raw Axis payloads into internal event format. (NOT USED IN THE MAIN LIVE INGESTION PATH)
|   |   |-- source/              # Provides readers and raw event models for loading saved JSON/JSONL event streams
|   |   |-- storage/             # Storage helpers for raw ingestion data, to save live MQTT events to JSONL so they can be replayed.
|   |   `-- validation/          # Validation of incoming event payloads. (NOT USED IN THE MAIN LIVE INGESTION PATH)
|   |-- analysis/                # Sets up LLM analysis clients and image utilities
|   |-- tests/
|   `-- requirements.txt         # Backend Python dependencies
|-- frontend/
|   |-- src/
|   |   |-- components/
|   |   |-- Features/
|   |   |-- Analys.jsx
|   |   |-- App.jsx
|   |   |-- Home.jsx
|   |   `-- main.jsx
|   |-- package.json
|   `-- vite.config.js
`-- .github/workflows/tests.yml
```

## Requirements

- Python 3.12 
- Node.js and npm
- RTSP access to the camera when running live ingestion
- Mosquitto as an MQTT broker for the live camera metadata
- A `FACADE_API_KEY` environment variable if you want to use the real LLM analysis endpoint

The project also uses the `sentence-transformers/all-MiniLM-L6-v2` embedding model. `init.py` downloads it into `backend/database/models/all-MiniLM-L6-v2` if it is missing.

## Setup

From the repository root:

```
python init.py
```

This script:

1. Creates `backend/.venv`.
2. Installs Python packages from `backend/requirements.txt`.
3. Downloads the local sentence-transformer model if needed.
4. Runs `npm install` in `frontend/`.

If you want to configure the real image analysis client, create a `.env` file or export the variable in your shell: 

```
FACADE_API_KEY=your_api_key_here
```

## Run the App

From the repository root:

```
python start.py
```

This starts:

- FastAPI backend on `http://127.0.0.1:8000`
- Vite frontend on `http://localhost:5173`

Open the frontend URL in your browser.

You can also start the services manually:

```
cd backend/database
python database.py
```

```
cd frontend
npm run dev
```

## Ingestion
The frontend and backend can run without ingestion, but search results only appear after analysis data has been stored.

### Running Live Camera 
Live camera ingestion is started from `backend/ingestion/camera.py`. That file creates a `Camera` object, which is responsible for connecting to the RTSP stream, listening for MQTT metadata, selecting frames, calling the analysis client, and saving results to the database.

Before running it, update the camera and broker settings in `backend/ingestion/camera.py`, especially:

- camera IP, username, and password
- MQTT broker host and port
- camera id
- analysis model settings

Then run it from `backend/` with the backend virtual environment active:

```
python3 ingestion/camera.py
```

When ingestion receives an MQTT event, it:

1. Stores the raw event as JSONL for debugging/replay.
2. Extracts event start/end timestamps and snapshot image data.
3. Finds the closest full-frame image in the RTSP hot buffer.
4. Selects uniform and movement-based frame sequences.
5. Sends selected images to the analysis client.
6. Saves descriptions and embeddings through the database layer.


### Running replay camera
#Todo explain how to start it and how it works 




## Backend API

Main endpoints from `backend/database/database.py`:

#Had chat schetch up  how i want it to look, just check that the information is  correct though
| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/event/{query}` | Search for the best matching analyzed event |
| `GET` | `/api/image/{description}` | Return an image for a stored description |
| `GET` | `/api/settings` | Load current analysis settings |
| `POST` | `/api/settings` | Save analysis settings |
| `GET` | `/api/stats` | Return feedback totals for the active settings |
| `POST` | `/api/feedback` | Store a 0-5 rating for a result type |
| `POST` / `PATCH` | `/api/admin/reset` | Clear the SQLite database and recordings for camera `1` |

#TODO: A short explaination on how the embedding search works


## Database Model

#TODO: List important tables and what they do and what they store:


## Frontend

#TODO: Explain what the frontend is built on, (React, vite etc). 

#TODO Explain/list the main views and components and explain what they do (kinda like the database)

Main views:

Main components:



## Settings
#Todo: Mention what settings there are and what they do 




## Tests

The project includes automated tests for the backend, database layer, live ingestion logic, and simulated camera/replay flow.

Most tests are written with `pytest` and are located under:

- `backend/tests/`
- `backend/database/database_unit_tests.py`

### Running tests

From `GR8/backend`:

```bash
source venv/bin/activate
python -m pytest tests database/database_unit_tests.py -q
```

For more test output:

```bash
python -m pytest tests database/database_unit_tests.py -v
```


The test suite is also run automatically in GitHub Actions through
- `.github/workflows/tests.yml`

This helps catch regressions before changes are merged.