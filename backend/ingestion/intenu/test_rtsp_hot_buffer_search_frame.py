from __future__ import annotations

"""
RTSP hot buffer integration test (manuell körning).
Kopplat till krav F04 "Synkronisera inkommande metadata med tillhörande bildrutor baserat på timestamps"
Kopplat till krav F08 "Logik för att hämta högupplösta bildrutor från videoströmmen som matchar tidpunkten."

Varför testet finns:
- Verifiera att hot buffern faktiskt innehåller RTSP-frame-data.
- Verifiera att vi kan slå upp "närmsta frame" med hjälp av en timestamp.
- Verifiera att frame-datan går att använda vidare (base64 + skriva ut JPG-fil).

Detta är INTE ett snabbt unit-test:
- Testet kräver riktig RTSP-källa (kamera/stream).
- Testet kräver lokala beroenden (cv2 + paho).
- Testet körs därför endast när env flagga sätts:
  RUN_RTSP_HOT_BUFFER_TEST=1

Vad man ska titta efter i terminalen:
1) "RTSP hot buffer stats: {...}" med frames > 0 och bytes > 0
2) "Nearest frame: ..." med target_ts och frame_ts nära varandra
3) "base64_len=..." > 0
4) "Wrote debug_latest_test.jpg" + "Wrote debug_nearest_test.jpg"
5) "Segments found: N" där N > 0

Vad man ska titta efter i filsystemet:
- `debug_latest_test.jpg` och `debug_nearest_test.jpg` ska skapas.
- Båda ska gå att öppna som riktiga bilder från streamen.
- `recordings/<camera_id>/` ska innehålla MP4-segment.

Vad testet bevisar:
- End-to-end i hot buffer-spåret:
  RTSP -> capture -> hot buffer -> search_frame(timestamp) -> bytes -> base64/JPG.
- Att ffmpeg-segmentering är igång parallellt (MP4 skrivs till recordings).

FÖR ATT KÖRA TESTET SMATTRA IN DETTA I TERMINALEN:
cd GR8/backend
RUN_RTSP_HOT_BUFFER_TEST=1 \
RTSP_URL='rtsp://student:student@192.168.0.90/axis-media/media.amp' \
python3 -m ingestion.tests.test_rtsp_hot_buffer_search_frame
"""

import base64
import importlib.util
import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from time import sleep


RUN_RTSP_TEST = os.getenv("RUN_RTSP_HOT_BUFFER_TEST") == "1"


@unittest.skipUnless(
    RUN_RTSP_TEST,
    "Set RUN_RTSP_HOT_BUFFER_TEST=1 to run this integration test.",
)
class RtspHotBufferSearchFrameTest(unittest.TestCase):
    def test_search_frame_returns_nearest_and_is_convertible_to_base64(self) -> None:
        # Skydda testet: om beroenden saknas skippar vi med tydlig orsak.
        if importlib.util.find_spec("cv2") is None:
            self.skipTest("cv2 is required for RTSP hot buffer integration test.")
        if importlib.util.find_spec("paho") is None:
            self.skipTest("paho-mqtt is required for Camera import in this test.")
        if importlib.util.find_spec("imageio_ffmpeg") is None:
            self.skipTest("imageio-ffmpeg is required for recording verification in this test.")

        import imageio_ffmpeg
        from ingestion.camera import Camera

        class _NoMqttCamera(Camera):
            def init_mqtt(self, broker_host: str, broker_port: int) -> None:
                # RTSP hot buffer verification does not require MQTT.
                return

        rtsp_url = os.getenv("RTSP_URL")
        self.assertTrue(rtsp_url, "RTSP_URL env var must be set for RTSP integration test.")

        # Konfigurerbar väntetid så hot buffer hinner fyllas.
        wait_seconds = int(os.getenv("RTSP_HOT_BUFFER_WAIT_SECONDS", "20"))
        segment_seconds = int(os.getenv("RTSP_SEGMENT_SECONDS", "5"))
        nearest_file = Path(os.getenv("RTSP_DEBUG_NEAREST_FILE", "debug_nearest_test.jpg"))
        latest_file = Path(os.getenv("RTSP_DEBUG_LATEST_FILE", "debug_latest_test.jpg"))
        camera_id = os.getenv("RTSP_CAMERA_ID", "1")
        ffmpeg_path = os.getenv("FFMPEG_PATH") or imageio_ffmpeg.get_ffmpeg_exe()
        recordings_dir = Path("recordings") / camera_id

        # Kamera startas med recording + hot buffer, men utan MQTT.
        camera = _NoMqttCamera(
            camera_id=camera_id,
            rtsp_url=rtsp_url,
            ffmpeg=ffmpeg_path,
            broker_host="127.0.0.1",
            broker_port=1883,
            segment_seconds=segment_seconds,
            hot_buffer_seconds=30,
            hot_buffer_fps=5,
        )

        try:
            # 1) Låt buffern fyllas med frames.
            sleep(wait_seconds)
            stats = camera.hot_buffer_stats()
            self.assertGreater(stats["frames"], 0, f"No frames captured. stats={stats}")
            self.assertGreater(stats["bytes"], 0, f"No bytes captured. stats={stats}")

            # 2) Sök närmaste frame för aktuell timestamp.
            target_ts = datetime.now(timezone.utc)
            nearest = (
                camera.frame_buffer.search_frame(target_ts)
                if camera.frame_buffer is not None
                else None
            )
            self.assertIsNotNone(nearest, "search_frame returned None.")

            assert nearest is not None
            # 3) Verifiera att frame-bytes går att base64-koda (typisk transportväg).
            frame_b64 = base64.b64encode(nearest.jpeg_bytes).decode("ascii")
            self.assertGreater(len(frame_b64), 0, "Base64 conversion produced empty string.")

            # 4) Skriv både latest och nearest frame till disk för visuell kontroll.
            wrote_latest = camera.dump_latest_hot_buffer_frame(str(latest_file))
            self.assertTrue(wrote_latest, "Failed to write latest debug frame.")
            nearest_file.write_bytes(nearest.jpeg_bytes)

            # 5) Verifiera att recording-segment faktiskt skapats.
            self.assertTrue(recordings_dir.exists(), f"Recordings folder missing: {recordings_dir}")
            segments = sorted(recordings_dir.glob("*.mp4"))
            self.assertGreater(len(segments), 0, f"No MP4 segments created in {recordings_dir}")

            # Debug-utskrift för manuell verifiering i terminal.
            print("RTSP hot buffer stats:", stats)
            print(
                "Nearest frame:",
                f"target_ts={target_ts.isoformat()}",
                f"frame_ts={nearest.timestamp.isoformat()}",
                f"size={nearest.width}x{nearest.height}",
                f"base64_len={len(frame_b64)}",
            )
            print("base64_preview:", frame_b64[:160], "...")
            print(f"Wrote {latest_file}")
            print(f"Wrote {nearest_file}")
            print(f"Recordings folder: {recordings_dir}")
            print(f"Segments found: {len(segments)}")
        finally:
            camera.stop_recording()


if __name__ == "__main__":
    unittest.main()
