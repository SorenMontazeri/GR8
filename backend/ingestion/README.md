# Ingestion Module

Detta dokument beskriver ingestion-modulens ansvar, dataflöde och hur ni kör/testar den.

## Syfte

Ingestion tar in rå eventdata (live via MQTT eller replay från fil, alltså consolidated data), validerar det, mappar till ett internt format (`InternalEvent`) och skickar vidare till nästa steg via en dispatcher.

## Översikt: Dataflöde

1. **Källa**
- Live: `camera.py:on_message()` tar emot MQTT-payload.
- Replay: `source/replay_reader.py:iter_replay_events()` läser JSON/JSONL.

2. **Raw event**
- Data paketeras som `RawEvent` med metadata som `received_at` och `source`.

3. **Validering**
- `validation/validator.py:validate_raw_event()` kontrollerar grundkrav och klassar eventtyp.

4. **Normalisering**
- `normalization/mapper.py` mappar Axis-payload till `InternalEvent`.
- `track_id` sätts från `payload["id"]` enligt nuvarande beslut.

5. **Dispatch**
- `ingestion_service.py` skickar `InternalEvent` via `dispatcher.dispatch(...)`.
- `dispatch/dispatcher.py` innehåller kontraktet (`Dispatcher`) och `DirectDispatcher`.

## Liveflöde (`camera.py`)

`Camera` ansvarar för:
- start/stop av segmentinspelning via `record_ffmpeg.py`
- MQTT-lyssning
- RTSP hot buffer (frame-ringbuffer)

### Hot buffer

Hot buffern består av:
- `BufferedFrame`: timestamp + JPEG-bytes + dimensioner
- `FrameRingBuffer`: trådsäker ringbuffer med trimning

Standardkonfiguration:
- tidsfönster: 30 sekunder
- sampling: 5 FPS
- max antal frames: 150
- max minne: 50 MB (trimmas FIFO vid överskridning)
- JPEG-kvalitet: 70
- nedskalning: max bredd 960 px

Detta gör att bufferten håller stabil minnesnivå över tid.

## Filansvar

- `ingestion_service.py`: orchestration (validate -> map -> dispatch)
- `camera.py`: live MQTT + RTSP hot buffer + recording lifecycle
- `record_ffmpeg.py`: ffmpeg-baserad inspelning/segmentering
- `dispatch/dispatcher.py`: dispatch-kontrakt och direct-dispatch
- `source/replay_reader.py`: replayläsning och `RawEvent`-modell
- `validation/validator.py`: grundvalidering av råhändelser
- `normalization/mapper.py`: Axis -> `InternalEvent`
- `queue/event_buffer.py`: kö-wrapper (bakåtkompatibilitet/fallback)
- `tests/run_replay_test.py`: enkel replay-kedjetest
- `tests/test_live_camera.py`: live/on_message + hotbuffer-tester

## Körning

Kör från `GR8/backend`.

Replay-smoke test:

```bash
python3 -m ingestion.tests.run_replay_test
```

Live/hotbuffer tester:

```bash
python3 -m ingestion.tests.test_live_camera
```


## Nuvarande testtäckning

`tests/test_live_camera.py` täcker:
- `on_message()` med giltig JSON
- `on_message()` felhantering (trasig JSON, tom payload)
- integration: live-liknande payload -> `InternalEvent` dispatchas
- `FrameRingBuffer` gränser för `max_frames` och `max_bytes`

`tests/run_replay_test.py` verifierar replayflödet end-to-end.

## Vanliga fel och felsökning

- `ModuleNotFoundError: ingestion`
  - Kör från `GR8/backend` och sätt `PYTHONPATH=.`
- `ModuleNotFoundError: cv2` eller `paho`
  - Installera beroenden från `backend/requirements.txt` i aktiv miljö
- MQTT-meddelanden parseas inte
  - Kontrollera JSON-format och topic `camera/<camera_id>`
- RTSP reconnect-loop
  - Kontrollera RTSP URL, användare/lösenord och nätverk
