# Ingestion Module

Detta dokument beskriver ingestion-modulens ansvar, dataflöde och hur ni kör/testar den.

## Syfte

Ingestion tar in rå eventdata (live via MQTT eller replay från fil, alltså consolidated data), validerar det, mappar till ett internt format (`InternalEvent`) och skickar vidare till nästa steg via callback.

Notera: live-vägen i `camera.py` använder just nu hotbuffer + analysclient direkt.
Replay-vägen använder `ingestion_service.py` med validering/mappning.

## Installation

För att en helt ny användare ska kunna köra ingestion och den simulerade kameran behövs två typer av beroenden:

1. Python-beroenden för backend
2. Externa systemverktyg för RTSP och MQTT

### 1. Python-beroenden

Kör från `GR8/backend`:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Detta installerar bland annat:
- `fastapi`
- `uvicorn`
- `pytest`
- `pytest-cov`
- `httpx`
- `python-dotenv`
- `opencv-python`
- `imageio-ffmpeg`
- `paho-mqtt`

### 2. Externa systemverktyg

Den simulerade kameran kräver också:
- `mediamtx` för RTSP-server
- `mosquitto` för MQTT-broker

Dessa installeras inte via `pip` och ligger därför inte i `requirements.txt`.

På macOS med Homebrew:

```bash
brew install mediamtx mosquitto
```

Kontrollera gärna att de finns:

```bash
mediamtx --version
mosquitto -h | head
```

### 3. Frontend

Om du även vill testa sökning i UI behövs Node/npm.

Kör från `GR8/frontend`:

```bash
npm install
```

### 4. Valfritt: riktig analys

Om ingestion ska använda riktig analysmodell i stället för stub-analys behövs:

```bash
export FACADE_API_KEY='din_nyckel'
```

Om ingen nyckel finns kan ni fortfarande testa flödet med stub-analys.

## Översikt: Dataflöde

1. **Källa**
- Live: `camera.py:on_message()` tar emot MQTT-payload.
- Replay: `source/replay_reader.py:iter_replay_events()` läser JSON/JSONL.

2. **Raw event (replay-vägen)**
- Replay-data paketeras som `RawEvent` med metadata som `received_at` och `source`.

3. **Validering**
- `validation/validator.py:validate_raw_event()` kontrollerar grundkrav och klassar eventtyp.

4. **Normalisering**
- `normalization/mapper.py` mappar Axis-payload till `InternalEvent`.
- `track_id` sätts från `payload["id"]` enligt nuvarande beslut.

5. **Forwarding**
- `ingestion_service.py` skickar `InternalEvent` via en enkel callback (`on_internal_event`).

6. **Live context-matchning (`camera.py`)**
- MQTT-event läggs i `MqttEventRingBuffer`.
- Närmaste RTSP-frame hämtas via timestamp.
- `camera.get_context_at(...)` kan returnera både frame och matchande MQTT-event.

## Liveflöde (`camera.py`)

`Camera` ansvarar för:
- start/stop av segmentinspelning via `record_ffmpeg.py`
- MQTT-lyssning
- RTSP hot buffer (frame-ringbuffer)
- MQTT hot buffer (event-ringbuffer)
- analysanrop + persistens (`save_analysis`) när context hittas

### Hot buffer

Hot buffern består av:
- `BufferedFrame`: timestamp + JPEG-bytes + dimensioner
- `FrameRingBuffer`: trådsäker ringbuffer med trimning
- `BufferedMqttEvent`: timestamp + rå MQTT-payload
- `MqttEventRingBuffer`: trådsäker ringbuffer för MQTT-event

Standardkonfiguration:
- tidsfönster: 30 sekunder
- sampling: 5 FPS
- max antal frames: 150
- max minne: 50 MB (trimmas FIFO vid överskridning)
- max MQTT-events: 300
- max MQTT-buffer: 5 MB (trimmas FIFO vid överskridning)
- JPEG-kvalitet: 70
- nedskalning: max bredd 960 px

Detta gör att bufferten håller stabil minnesnivå över tid.

## Filansvar

- `ingestion_service.py`: orchestration (validate -> map -> callback)
- `camera.py`: live MQTT + RTSP hot buffer + recording lifecycle
- `simulator/`: virtuell livekamera som spelar scenario som RTSP + MQTT
- `buffers/rtsp_hot_buffer.py`: datastruktur + lookup för RTSP hot buffer
- `buffers/mqtt_event_buffer.py`: datastruktur + lookup för MQTT hot buffer
- `record_ffmpeg.py`: ffmpeg-baserad inspelning/segmentering
- `source/replay_reader.py`: replayläsning och `RawEvent`-modell
- `validation/validator.py`: grundvalidering av råhändelser
- `normalization/mapper.py`: Axis -> `InternalEvent`
- `tests/ingestion_tests/test_ingestion_replay_pipeline.py`: enkel replay-kedjetest
- `tests/ingestion_tests/test_ingestion_live_camera.py`: live/on_message + hotbuffer-tester
- `tests/ingestion_tests/test_ingestion_rtsp_hot_buffer_search_frame.py`: manuell RTSP-integration
- `tests/ingestion_tests/test_ingestion_mqtt_context_matching.py`: matchning frame + MQTT-event via timestamp
- `tests/ingestion_tests/test_ingestion_simulated_camera.py`: unit-tester för simulatorns scenario/tidsomskrivning/MQTT-schemaläggning
- `tests/ingestion_tests/test_ingestion_simulated_live_camera_e2e.py`: manuellt end-to-end-test för simulerad livekamera

## Simulerad livekamera

Simulatorn låter er spela upp ett inspelat scenario som om det vore en riktig livekamera.

V1 bygger på:
- extern RTSP-server, rekommenderat MediaMTX
- extern MQTT-broker
- scenarioformat: `video.mp4` + `events.jsonl`

Simulatorns ansvar:
- pusha video till RTSP-server i realtid via ffmpeg
- läsa JSONL med rå MQTT-payloads
- räkna fram offset från originaltider
- skriva om tidsfält till nutid
- publicera omskrivna events på `camera/<camera_id>`

Det går även att köra simulatorn i RTSP-only-läge utan MQTT:
- använd `--no-mqtt`
- då behövs ingen eventfil och ingen broker
- bra för att verifiera att videoströmmen fungerar innan ni testar metadata-matchning

Det går även att köra simulatorn i kontinuerligt loop-läge:
- använd `--loop`
- då loopas både RTSP-video och MQTT-scenario tills processen avbryts
- bra när ni vill låta ingestion/analys ligga uppe länge och observera riktiga attribututskrifter

Viktigt:
- `camera.py` försöker nu använda `start_time` från MQTT-payload.
- Om `start_time` saknas eller är trasig faller den tillbaka till `datetime.now(timezone.utc)`.
- Därför måste simulatorn skriva om eventtiderna till nutid innan publicering.

Kör simulatorn från `GR8/backend`:

```bash
PYTHONPATH=. python3 -m ingestion.simulator.simulated_camera \
  --video path/to/video.mp4 \
  --events path/to/events.jsonl \
  --camera-id sim-1 \
  --broker-host 127.0.0.1 \
  --broker-port 1883 \
  --rtsp-publish-url rtsp://127.0.0.1:8554/sim-1 \
  --loop
```

Det finns även en orkestrerare för hela appstacken för E2E-test:

```bash
cd GR8/backend
source .venv/bin/activate
python run_simulated_stack.py \
  --camera-id 1 \
  --api-key "$FACADE_API_KEY"
```

Det scriptet startar:
- ingestion
- database API
- frontend

och skriver allt i samma terminal med prefixade loggar.

Om du bara vill starta den simulerade kameran och infrastrukturen, men köra ingestion separat:

```bash
cd GR8/backend
source .venv/bin/activate
python run_simulated_camera.py \
  --video recordings/1/D2026-02-24-T13-16-48.mp4 \
  --events replay_out/scenario_2026-02-24_131648.jsonl \
  --camera-id 1 \
  --loop
```

Det scriptet startar:
- `mediamtx`
- `mosquitto`
- simulatorn

och skriver sedan ut RTSP-URL och MQTT-topic som ingestion kan ansluta mot.

För att starta ingestion separat mot en live eller simulerad källa:

```bash
cd GR8/backend
source .venv/bin/activate
python run_ingestion.py \
  --camera-id 1 \
  --rtsp-url rtsp://127.0.0.1:8554/1 \
  --broker-host 127.0.0.1 \
  --broker-port 1883
```

Med riktig analys:

```bash
cd GR8/backend
source .venv/bin/activate
export FACADE_API_KEY='din_nyckel'
python run_ingestion.py \
  --camera-id 1 \
  --rtsp-url rtsp://127.0.0.1:8554/1 \
  --broker-host 127.0.0.1 \
  --broker-port 1883
```

Med stub-analys:

```bash
python run_ingestion.py \
  --camera-id 1 \
  --rtsp-url rtsp://127.0.0.1:8554/1 \
  --broker-host 127.0.0.1 \
  --broker-port 1883 \
  --stub-analysis
```

RTSP-only:

```bash
PYTHONPATH=. python3 -m ingestion.simulator.simulated_camera \
  --video path/to/video.mp4 \
  --camera-id sim-1 \
  --rtsp-publish-url rtsp://127.0.0.1:8554/sim-1 \
  --no-mqtt
```

Ingestion kan sedan ansluta transparent mot:
- RTSP read URL: `rtsp://127.0.0.1:8554/sim-1`
- MQTT topic: `camera/sim-1`

### Rekommenderad lokal MediaMTX-konfiguration

För att undvika skillnader mellan olika lokala MediaMTX-installationer finns en minimal projektkonfiguration i:
- `backend/mediamtx.yml`

Starta gärna RTSP-servern explicit med den filen:

```bash
cd GR8/backend
mediamtx mediamtx.yml
```

Den konfigurationen:
- öppnar RTSP på `:8554`
- använder endast TCP för RTSP
- accepterar publisher-baserade paths
- har en explicit path för `sim-1`

## Körning

Kör från `GR8/backend`.

Replay-smoke test:

```bash
PYTHONPATH=. python3 tests/ingestion_tests/test_ingestion_replay_pipeline.py
```

Live/hotbuffer tester:

```bash
PYTHONPATH=. python3 -m unittest tests.ingestion_tests.test_ingestion_live_camera -v
```

Simulator-unit tester:

```bash
PYTHONPATH=. python3 -m unittest tests.ingestion_tests.test_ingestion_simulated_camera -v
```

RTSP hot buffer integrationstest (manuellt):

```bash
RUN_RTSP_HOT_BUFFER_TEST=1 \
RTSP_URL='rtsp://student:student@192.168.0.90/axis-media/media.amp' \
PYTHONPATH=. python3 -m unittest tests.ingestion_tests.test_ingestion_rtsp_hot_buffer_search_frame -v
```

Simulerad livekamera E2E-test (manuellt):

```bash
RUN_SIMULATED_LIVE_E2E_TEST=1 \
SIM_VIDEO='path/to/video.mp4' \
SIM_EVENTS='path/to/events.jsonl' \
SIM_CAMERA_ID='sim-1' \
SIM_RTSP_PUBLISH_URL='rtsp://127.0.0.1:8554/sim-1' \
SIM_RTSP_READ_URL='rtsp://127.0.0.1:8554/sim-1' \
SIM_BROKER_HOST='127.0.0.1' \
SIM_BROKER_PORT='1883' \
PYTHONPATH=. python3 -m unittest tests.ingestion_tests.test_ingestion_simulated_live_camera_e2e -v
```

Praktisk E2E-körning i fyra terminaler:

1. RTSP-server:

```bash
cd GR8/backend
mediamtx mediamtx.yml
```

2. MQTT-broker:

```bash
mosquitto -p 1883
```

3. Simulerad kamera:

```bash
cd GR8/backend
source .venv/bin/activate
PYTHONPATH=. python3 -m ingestion.simulator.simulated_camera \
  --video recordings/1/D2026-02-24-T13-16-48.mp4 \
  --events replay_out/scenario_2026-02-24_131648.jsonl \
  --camera-id sim-1 \
  --broker-host 127.0.0.1 \
  --broker-port 1883 \
  --rtsp-publish-url rtsp://127.0.0.1:8554/sim-1 \
  --loop
```

4. Ingestion mot simulatorn:

```bash
cd GR8/backend
source .venv/bin/activate
PYTHONPATH=. python3 - <<'PY'
import os
import time
import imageio_ffmpeg

from ingestion.camera import Camera
from analysis.sync_prisma import LLMClientSync

endpoint = "https://api.ai.auth.axis.cloud/v1/chat/completions"
api_key = os.environ.get("FACADE_API_KEY")
model = "prisma_gemini_pro"

llm = LLMClientSync(endpoint, api_key, model)
camera = Camera(
    camera_id="sim-1",
    rtsp_url="rtsp://127.0.0.1:8554/sim-1",
    ffmpeg=imageio_ffmpeg.get_ffmpeg_exe(),
    broker_host="127.0.0.1",
    broker_port=1883,
    analysis_client=llm,
    segment_seconds=5,
)

try:
    time.sleep(15)
    print("Hot buffer stats:", camera.hot_buffer_stats())
    print("MQTT buffer stats:", camera.mqtt_buffer_stats())
finally:
    camera.stop_recording()
PY
```

Förväntat resultat:
- simulatorn skriver `Simulation completed: ...`
- MediaMTX visar att publisher/readers ansluter till path `sim-1`
- ingestion-processen visar att hot buffer och MQTT-buffer innehåller data
- om analysklienten är korrekt konfigurerad skrivs `keywords` ut när MQTT-event matchas mot en frame

## Nuvarande testtäckning

`tests/ingestion_tests/test_ingestion_live_camera.py` täcker:
- `on_message()` med giltig JSON
- `on_message()` felhantering (trasig JSON, tom payload)
- integration: live-liknande payload -> frame hämtas + analys sparas
- `FrameRingBuffer` gränser för `max_frames` och `max_bytes`

`tests/ingestion_tests/test_ingestion_mqtt_context_matching.py` täcker:
- MQTT hot buffer lookup med toleransfönster
- Kontextmatchning (`get_context_at`) mellan RTSP-frame och MQTT-event

`tests/ingestion_tests/test_ingestion_replay_pipeline.py` verifierar replayflödet end-to-end.

## Vanliga fel och felsökning

- `ModuleNotFoundError: ingestion`
  - Kör från `GR8/backend` och sätt `PYTHONPATH=.`
- `ModuleNotFoundError: cv2` eller `paho`
  - Installera beroenden från `backend/requirements.txt` i aktiv miljö
- MQTT-meddelanden parseas inte
  - Kontrollera JSON-format och topic `camera/<camera_id>`
- RTSP reconnect-loop
  - Kontrollera RTSP URL, användare/lösenord och nätverk
