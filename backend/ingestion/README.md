# Ingestion

Den här mappen innehåller live-ingestion, simulatorn för replay och några äldre byggstenar för validering/normalisering av rå eventdata.

Det viktiga att förstå är att projektet idag har två huvudsakliga körvägar:

1. Live-ingestion via `backend/run_ingestion.py`
2. Simulerad kamera via `backend/run_simulated_camera.py`

Den äldre `ingestion_service.py`-pipen finns kvar, men den är inte huvudvägen när ni kör vanlig livekamera idag.

## Nuvarande entrypoints

### Live-ingestion
Startas från `backend/run_ingestion.py`.

Det skriptet:
- skapar ett `Camera`-objekt
- kopplar upp RTSP
- kopplar upp MQTT
- startar videosegmentering
- tar emot metadata
- kör analys
- sparar resultat i databasen

Exempel:

```bash
cd GR8/backend
source venv/bin/activate
export FACADE_API_KEY='din_nyckel'

python run_ingestion.py \
  --camera-id 1 \
  --rtsp-url 'rtsp://student:student@192.168.0.90/axis-media/media.amp' \
  --broker-host 10.255.255.1 \
  --broker-port 1883 \
  --hot-buffer-backend gstreamer
```

Viktiga flaggor:
- `--hot-buffer-backend {gstreamer,opencv}`
- `--no-recording`
- `--no-mqtt`
- `--stub-analysis`
- `--raw-events-output`

### Simulerad kamera
Startas från `backend/run_simulated_camera.py`.

Det skriptet:
- startar lokal RTSP-server via MediaMTX
- startar lokal MQTT-broker via Mosquitto
- bygger eller väljer en scenario-video
- replayar rå MQTT-events i realtid
- publicerar RTSP på `rtsp://127.0.0.1:8554/<camera_id>`

Exempel:

```bash
cd GR8/backend
source venv/bin/activate

python run_simulated_camera.py \
  --segment-range 305:315 \
  --camera-id 1 \
  --events replay_out/live/camera_1_20260503T211120Z.jsonl
```

När simulatorn kör används normalt följande ingest-config:

```bash
python run_ingestion.py \
  --camera-id 1 \
  --rtsp-url 'rtsp://127.0.0.1:8554/1' \
  --broker-host 127.0.0.1 \
  --broker-port 1883 \
  --hot-buffer-backend opencv
```

`opencv` är ofta mer robust för simulatorn i den här miljön, medan `gstreamer` är den bättre varianten när man vill hålla sig närmare kameratid i live-flödet.

## Viktigaste filer

### `camera.py`
Det här är den centrala live-klassen.

`Camera` ansvarar för:
- MQTT-subscription på `camera/<camera_id>`
- hot buffer för videoframes
- segmentinspelning
- rå eventlagring till JSONL
- snapshot/full-frame/sequence-urval
- LLM-anrop
- sparning till `analysis.sqlite`

Det är här den faktiska live-analyslogiken ligger.

### `gstreamer_recorder.py`
Ansvarar för inspelning av RTSP-video till segment och för indexeringen av segmentens tider.

Den skriver:
- videosegment under `backend/recordings/<camera_id>/`
- indexrader till `backend/indexes/index-<camera_id>.csv`

Den är viktig eftersom frontend senare använder indexet för att koppla timestamps till video.

### `gstreamer_hot_buffer.py` och `opencv_hot_buffer.py`
Detta är två backend-val för hot buffer.

De används för att hålla ett kort glidande minne av videoframes som kan matchas mot MQTT-event.

- `gstreamer_hot_buffer.py`
  - bättre när målet är kameratidsbaserad synk
  - känsligare för RTSP/GStreamer-problem

- `opencv_hot_buffer.py`
  - enklare och robustare
  - använder lokal maskintid i stället för riktig kameratid

### `analysis/frame_selection.py`
Här ligger det settings-styrda frame-urvalet.

Det används idag av `camera.py` för att bygga två sekvenser:

- uniform sequence
- movement/varied sequence

Det är alltså här analysinställningarna för samplingsbeteende faktiskt får effekt.

### `simulator/`
Här ligger replayflödet för simulerad livekamera.

Viktigaste filerna:
- `simulated_camera.py`
- `rtsp_streamer.py`
- `mqtt_replayer.py`
- `scenario_loader.py`
- `timestamp_rewriter.py`

De här filerna används när ni vill spela upp gammal video + gamla events som om de kom live.

## Övergripande liveflöde

När ni kör live via `run_ingestion.py` ser flödet ut så här:

1. `Camera` startar recorder
2. `Camera` startar hot buffer
3. `Camera` kopplar upp MQTT
4. MQTT-event tas emot i `camera.py:on_message()`
5. Rå event sparas som JSONL för replay
6. Snapshot hämtas från `payload["image"]["data"]`
7. Full-frame hämtas från hot buffer om matchning lyckas
8. Uniform och varied sequence väljs
9. Bilder skickas till analysklienten
10. Resultat sparas i databasen via `save_description_bundle(...)`

## Settings-styrt frame selection

Frame selection styrs idag via `backend/database/settings.json` och API:t i `backend/database/database.py`.

Själva logiken ligger i:
- `backend/ingestion/analysis/frame_selection.py`

Det finns två huvudspår:

### Uniform
`frame_selection_uniform(...)`

Använder inställningar som:
- `uniform_samplerate`
- `uniform_samplerate_value`

Den väljer frames jämnt över eventets tidsintervall.

### Movement / Varied
`frame_selection_movement(...)`

Använder inställningar som:
- `movement_tracker_type`
- `movement_tracker_type_threshhold`
- `movement_samplerate`
- `movement_samplerate_value`

Den försöker välja frames baserat på visuell förändring i stället för bara jämn sampling.

## Simulerat liveflöde

När ni kör simulatorn ser flödet ut så här:

1. `run_simulated_camera.py` startar MediaMTX
2. `run_simulated_camera.py` startar Mosquitto
3. video väljs antingen direkt eller byggs från ett segmentintervall
4. eventfil filtreras till rätt tidsfönster om `--segment-range` används
5. `simulated_camera.py` startar RTSP-publicering via ffmpeg
6. `mqtt_replayer.py` publicerar MQTT-event i realtid
7. vanlig ingestion kan sedan ansluta mot:
   - RTSP: `rtsp://127.0.0.1:8554/1`
   - MQTT: `127.0.0.1:1883`

Det här gör att simulatorn beter sig nära en riktig livekamera, men på återspelbar data.

## Filer som fortfarande finns men inte är huvudvägen

### `ingestion_service.py`
Det här är en äldre eller mer generisk pipeline för:
- `RawEvent`
- validering
- normalisering
- callback

Den är fortfarande användbar som byggsten och för replay/struktur, men den är inte den centrala live-vägen idag.

### `validation/validator.py` och `normalization/mapper.py`
De används tillsammans med `ingestion_service.py`.

Bra att behålla, men de beskriver inte hela dagens liveflöde.

## Rekommenderad mental modell

Om du bara ska förstå ingestion snabbt:

- `run_ingestion.py` startar liveflödet
- `camera.py` är kärnan
- `gstreamer_recorder.py` ansvarar för videosegment och index
- `gstreamer_hot_buffer.py` / `opencv_hot_buffer.py` levererar frames för analys
- `analysis/frame_selection.py` styr sequence-urval enligt settings
- `run_simulated_camera.py` replayar gamla sessions som ny “livekamera”

Det är den struktur som bäst motsvarar hur projektet faktiskt körs idag.
