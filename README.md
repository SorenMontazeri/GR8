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

```
.
|-- start.py                     # Starts backend API and frontend dev server
|-- init.py                      # Sets up backend and frontend dependencies
|-- backend/
|   |-- run_ingestion.py         # Main entrypoint for live camera ingestion
|   |-- run_simulated_camera.py  # Starts the replay simulator with local RTSP and MQTT
|   |-- database/
|   |   |-- database.py          # Contains the implementation for the database as well as the communication between frontend and backend
|   |   |-- settings.json        # Contains the current settings the analysis will run, as well as filter the search result to the current settings in frontend
|   |   `-- settings_editor.py   # Helpfunctions to handle settings.json
|   |-- ingestion/
|   |   |-- camera.py            # Connects RTSP video and MQTT events to the ingestion pipeline
|   |   |-- gstreamer_recorder.py # Records RTSP video segments and writes timestamp indexes
|   |   |-- gstreamer_hot_buffer.py # Hot buffer based on GStreamer, closer to camera timestamps
|   |   |-- opencv_hot_buffer.py # Hot buffer based on OpenCV, often more robust for replay
|   |   |-- simulator/           # Replay flow for simulated live camera using saved video and MQTT events
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
|   |   |-- Analys.jsx          # Compilation of number of likes
|   |   |-- App.jsx             # Navigation between homepage and analys page 
|   |   |-- Home.jsx            # Homepage at website
|   |   `-- main.jsx            # To start the React application 
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
The current live camera ingestion is started from `backend/run_ingestion.py`. It creates a `Camera` object, connects to the real RTSP camera stream, connects to the MQTT broker, starts video recording/segmenting, receives camera metadata, runs analysis, and saves the results to the database.

The live camera provides:

- RTSP video from the camera, for example `rtsp://student:student@192.168.0.90/axis-media/media.amp`
- MQTT events from the broker, usually on the topic `camera/<camera_id>`

Example:

```bash
cd GR8/backend
source venv/bin/activate
export FACADE_API_KEY='your_api_key_here'

python run_ingestion.py \
  --camera-id 1 \
  --rtsp-url 'rtsp://student:student@192.168.0.90/axis-media/media.amp' \
  --broker-host 10.255.255.1 \
  --broker-port 1883 \
  --hot-buffer-backend gstreamer
```

Useful flags for this entrypoint:

- `--hot-buffer-backend {gstreamer,opencv}`
- `--no-recording`
- `--no-mqtt`
- `--stub-analysis`
- `--raw-events-output`

`gstreamer` is usually the better hot buffer backend for live ingestion when you want to stay close to camera time. `opencv` is simpler and often more robust, but uses local machine time instead of real camera time.

Older direct camera entrypoint:

Live camera ingestion can also be started from `backend/ingestion/camera.py`. That file creates a `Camera` object, which is responsible for connecting to the RTSP stream, listening for MQTT metadata, selecting frames, calling the analysis client, and saving results to the database.

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
The replay camera uses the same ingestion flow as the live camera, but replaces the real camera and real MQTT broker with local simulated ones.

The simulated camera is started from `backend/run_simulated_camera.py`. It starts a local RTSP server through MediaMTX, starts a local Mosquitto MQTT broker, chooses or builds a scenario video, and replays saved MQTT events in real time.

Example:

```bash
cd GR8/backend
source venv/bin/activate

python run_simulated_camera.py \
  --segment-range 305:315 \
  --camera-id 1 \
  --events replay_out/live/camera_1_20260503T211120Z.jsonl
```

The simulator publishes:

- RTSP video at `rtsp://127.0.0.1:8554/<camera_id>`
- MQTT events on `127.0.0.1:1883`

Then start normal ingestion against the simulated camera:

```bash
python run_ingestion.py \
  --camera-id 1 \
  --rtsp-url 'rtsp://127.0.0.1:8554/1' \
  --broker-host 127.0.0.1 \
  --broker-port 1883 \
  --hot-buffer-backend opencv
```

After this, `run_ingestion.py` behaves like it does for the live camera: it connects to RTSP and MQTT, receives events, selects frames, calls analysis, and stores the result bundle in the database.

Replay-specific differences:

- RTSP points to the local simulator instead of the real camera.
- MQTT points to the local broker instead of the live camera broker.
- Saved JSONL events are replayed in real time.
- `opencv` is usually the most robust hot buffer backend for replay.




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

The embedded search will return the description with the highest point value. If a snapshot analysis has a good point, it will return the ID of that snapshot. 
Frontend will then get all the different analysis responds that has that ID (the same event). 


## Database Model

Important tables in `backend/database/analysis.sqlite`:

- `description_group` links one event together. It stores the event start/end timestamps, references to the snapshot, full-frame, uniform sequence, and varied sequence rows, plus the settings used when the event was analyzed.
- `snapshot_description` stores the camera snapshot from the MQTT event, the LLM description, embedding, token count, timestamp, and feedback score.
- `full_frame_description` stores the matched full video frame from the RTSP hot buffer, the LLM description, embedding, token count, timestamp, and feedback score.
- `sequence_description_uniform` stores the time-based frame sequence, frame timestamps, images, LLM description, embedding, token count, and feedback score.
- `sequence_description_varied` stores the movement/variation-based frame sequence, frame timestamps, images, LLM description, embedding, token count, and feedback score.
- `app_settings` stores the latest saved frontend/backend analysis settings.
- `analysis` is an older/simple description table and is not the main table used by the current event bundle flow.

## Frontend

The frontend is built with React and Vite. Styling is done with Tailwind CSS classes, and frontend tests use Vitest with Testing Library.

The frontend talks to the FastAPI backend on `http://localhost:8000` and shows search results from the current SQLite data.

Main views:

- `Home.jsx` is the main search view. It contains the search field, settings panel, result images, sequence carousels, and rating controls.
- `Analys.jsx` shows feedback/statistics for the current settings and can reset the stored analysis data.
- `App.jsx` switches between the Home and Analys views and keeps search results and ratings in state while navigating.

Main components:

- `Settings.jsx` loads and saves analysis settings through `/api/settings`.
- `TextSearch.jsx` and `Searchbutton.jsx` handle the natural language search input.
- `FullFrame.jsx` and `Snapshot.jsx` show the single-image analysis results.
- `Sequence1.jsx` shows the uniform/time-based sequence description.
- `Sequence2.jsx` shows the movement/varied sequence description.
- `ImageCarousel.jsx` displays the selected sequence images.
- `StarRating.jsx` sends feedback scores for snapshot, full-frame, uniform, and varied results.


## Settings
Settings are stored in `backend/database/settings.json`, can be edited from the frontend, and are used during ingestion and search filtering.

- `min_event_duration` filters out events that are too short.
- `fullframe_time` decides when the full-frame image should be taken. `-1` means the same time as the snapshot; otherwise the value is a percentage of the event interval.
- `uniform_samplerate` chooses how the uniform sequence decides image count: auto, percent, or fixed number of frames.
- `uniform_samplerate_value` is the value used by the selected uniform sampling mode.
- `movement_tracker_type` chooses how movement-based selection works, either from MQTT boxes or visual image change.
- `movement_tracker_type_threshhold` controls how much visual change is required for movement-based selection.
- `movement_samplerate` chooses how many movement/varied frames are selected: auto, percent, or fixed number of frames.
- `movement_samplerate_value` is the value used by the selected movement sampling mode.
- `prompt_fullframe_snapshot` and `prompt_uniform_movement` are prompt fields for the LLM analysis client, but they are not currently exposed in the settings panel.



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
