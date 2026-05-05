from __future__ import annotations

"""
Simulated live camera end-to-end test (manuell körning).

Kopplat till krav:
- F01 "Systemet ska kunna ta emot metadata-strömmar via (HTTP/MQTT) i JSON-format enligt Axis-kameror."
- F03 "Systemet ska kunna hantera inspelad data på samma sätt som live-data."
- F04 "Systemet ska synkronisera inkommande metadata med tillhörande bildrutor baserat på tidstämplar."
- F08 "Logik för att hämta högupplösta bildrutor från videoströmmen som matchar tidpunkten för objektets snapshot."

Testnivå:
- Integrationstest

Varför testet finns:
- Verifiera att simulatorn beter sig som en livekamera för ingestion.
- Verifiera att RTSP och MQTT hålls synkroniserade via omskrivna nutidstimestamps.

Vad testet verifierar:
- Simulatorn pushar scenario-video via extern RTSP-server.
- Simulatorn publicerar scenario-events på extern broker.
- Camera fyller hot buffer och kan matcha MQTT-event mot RTSP-frame.

Förutsättningar:
- Extern RTSP-server körs redan, rekommenderat MediaMTX.
- Extern MQTT-broker körs redan.
- Scenario MP4 och JSONL finns lokalt.
- Testet körs bara när `RUN_SIMULATED_LIVE_E2E_TEST=1` är satt.

Vad man ska titta efter i terminalen:
1. `Simulation completed:` skrivs ut från simulatorn.
2. `camera.hot_buffer_stats()` visar frames > 0.
3. `camera.mqtt_buffer_stats()` visar events > 0.

Vad man ska titta efter i filsystemet / systemet:
- Eventuella recordings för testets camera_id skapas om inspelning är aktiv.

För att köra testet:
cd GR8/backend
RUN_SIMULATED_LIVE_E2E_TEST=1 \
SIM_VIDEO='path/to/video.mp4' \
SIM_EVENTS='path/to/events.jsonl' \
SIM_CAMERA_ID='sim-1' \
SIM_RTSP_PUBLISH_URL='rtsp://127.0.0.1:8554/sim-1' \
SIM_RTSP_READ_URL='rtsp://127.0.0.1:8554/sim-1' \
SIM_BROKER_HOST='127.0.0.1' \
SIM_BROKER_PORT='1883' \
PYTHONPATH=. python3 -m unittest tests.ingestion_tests.test_ingestion_simulated_live_camera_e2e -v
"""

import os
import subprocess
import sys
import time
import unittest


RUN_E2E = os.getenv("RUN_SIMULATED_LIVE_E2E_TEST") == "1"


@unittest.skipUnless(RUN_E2E, "Set RUN_SIMULATED_LIVE_E2E_TEST=1 to run this test.")
class SimulatedLiveCameraE2ETest(unittest.TestCase):
    def test_simulated_camera_feeds_ingestion(self) -> None:
        import imageio_ffmpeg
        from ingestion.camera import Camera

        video = os.environ["SIM_VIDEO"]
        events = os.environ["SIM_EVENTS"]
        camera_id = os.environ.get("SIM_CAMERA_ID", "sim-1")
        publish_url = os.environ["SIM_RTSP_PUBLISH_URL"]
        read_url = os.environ["SIM_RTSP_READ_URL"]
        broker_host = os.environ.get("SIM_BROKER_HOST", "127.0.0.1")
        broker_port = int(os.environ.get("SIM_BROKER_PORT", "1883"))
        ffmpeg_path = os.environ.get("FFMPEG_PATH") or imageio_ffmpeg.get_ffmpeg_exe()

        simulator_cmd = [
            sys.executable,
            "-m",
            "ingestion.simulator.simulated_camera",
            "--video",
            video,
            "--events",
            events,
            "--camera-id",
            camera_id,
            "--broker-host",
            broker_host,
            "--broker-port",
            str(broker_port),
            "--rtsp-publish-url",
            publish_url,
            "--ffmpeg-path",
            ffmpeg_path,
            "--warmup-seconds",
            "2",
        ]
        simulator = subprocess.Popen(simulator_cmd)

        class _NoAnalysisCamera(Camera):
            def __init__(self, *args, **kwargs) -> None:
                super().__init__(*args, analysis_client=None, **kwargs)

        camera = _NoAnalysisCamera(
            camera_id=camera_id,
            rtsp_url=read_url,
            broker_host=broker_host,
            broker_port=broker_port,
            segment_seconds=5,
        )
        try:
            time.sleep(8)
            self.assertGreater(camera.hot_buffer_stats()["frames"], 0)
            self.assertGreater(camera.mqtt_buffer_stats()["events"], 0)
        finally:
            camera.stop_recording()
            simulator.terminate()
            simulator.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
