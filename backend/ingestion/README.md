# Ingestion Module

Detta dokument beskriver ingestion-modulens ansvar, dataflöde och hur ni kör/testar den.

## Syfte

Ingestion tar in rå eventdata (live via MQTT eller replay från fil, alltså consolidated data), validerar det, mappar till ett internt format (`InternalEvent`) och skickar vidare till nästa steg via callback.

Notera: live-vägen i `camera.py` använder just nu hotbuffer + analysclient direkt.
Replay-vägen använder `ingestion_service.py` med validering/mappning.

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

### Möjliga analyslägen

Nuvarande live-beteende i `camera.py` är:
- MQTT-event -> närmaste frame i RTSP hot buffer -> analys -> `save_analysis(...)`

Om ni vill bygga ut detta vidare är tre naturliga analyslägen:

- `matched_frame`
  - nuvarande beteende
  - hämtar närmaste frame i RTSP hot buffer baserat på eventets timestamp
- `snapshot`
  - använder Axis snapshot direkt från MQTT-payloaden, typiskt `payload["image"]["data"]`
  - bra när man vill analysera den lilla, fokuserade delbilden istället för hela scenen
- `periodic_frame`
  - analyserar senaste frame i hot buffer med ett fast intervall, till exempel var 5:e sekund
  - användbart när analys inte ska vara beroende av att ett MQTT-event kommer exakt samtidigt
  - intervallet kan också räknas ut från total speltid, till exempel `duration / 10`, men aldrig snabbare än en analys per sekund

En bra struktur för detta är att låta alla lägen dela samma analysväg:
- välj bildkälla först
- skicka bilden till samma analysclient
- normalisera svaret till sökbara termer/keywords
- spara via `save_analysis(...)`

Obs:
- Replay-vägen i `ingestion_service.py` och `normalization/mapper.py` sparar idag inte hela snapshot-bilden i `InternalEvent`
- om snapshot-analys även ska fungera i replay behöver analysen ske före normalisering, eller så måste snapshot-data/referens bevaras

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

RTSP hot buffer integrationstest (manuellt):

```bash
RUN_RTSP_HOT_BUFFER_TEST=1 \
RTSP_URL='rtsp://student:student@192.168.0.90/axis-media/media.amp' \
PYTHONPATH=. python3 -m unittest tests.ingestion_tests.test_ingestion_rtsp_hot_buffer_search_frame -v
```

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
