import os
from datetime import datetime, timezone

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstRtp", "1.0")

from gi.repository import Gst, GstRtp, GLib


CAMERA_IP = "192.168.0.90"
USERNAME = "student"
PASSWORD = "student"

RTSP_URL = (
    f"rtsp://{USERNAME}:{PASSWORD}@{CAMERA_IP}"
    f"/axis-media/media.amp?camera=1&onvifreplayext=1"
)

RECORDING_DIR = "test_recordings"
SEGMENT_SECONDS = 10


def ntp_to_datetime(ntp_seconds, ntp_fraction):
    unix_time = ntp_seconds - 2208988800 + ntp_fraction / (1 << 32)
    return datetime.fromtimestamp(unix_time, timezone.utc)


def rtp_probe(pad, info):
    buffer = info.get_buffer()
    if not buffer:
        return Gst.PadProbeReturn.OK

    ok, rtp = GstRtp.RTPBuffer.map(buffer, Gst.MapFlags.READ)
    if not ok:
        return Gst.PadProbeReturn.OK

    marker = GstRtp.RTPBuffer.get_marker(rtp)

    ext = GstRtp.RTPBuffer.get_extension_data(rtp)
    if ext:
        ext_data, ext_id = ext

        if ext_id == 0xABAC and marker:
            payload = ext_data.get_data()

            ntp_seconds = int.from_bytes(payload[0:4], "big")
            ntp_fraction = int.from_bytes(payload[4:8], "big")

            camera_time = ntp_to_datetime(ntp_seconds, ntp_fraction)
            device_time = datetime.now(timezone.utc)

            diff_ms = (device_time - camera_time).total_seconds() * 1000

            print(
                f"camera={camera_time.isoformat()}  "
                f"device={device_time.isoformat()}  "
                f"diff_ms={diff_ms:.1f}"
            )

    GstRtp.RTPBuffer.unmap(rtp)
    return Gst.PadProbeReturn.OK


def main():
    Gst.init(None)

    os.makedirs(RECORDING_DIR, exist_ok=True)

    pipeline = Gst.parse_launch(
        f"""
        rtspsrc location="{RTSP_URL}" protocols=tcp latency=100
        ! application/x-rtp,media=video,encoding-name=H264
        ! identity name=rtp_probe silent=true
        ! rtph264depay
        ! h264parse config-interval=-1
        ! splitmuxsink
            location="{RECORDING_DIR}/segment-%05d.mkv"
            muxer-factory=matroskamux
            max-size-time={SEGMENT_SECONDS * 1_000_000_000}
        """
    )

    probe = pipeline.get_by_name("rtp_probe")
    probe_pad = probe.get_static_pad("src")
    probe_pad.add_probe(Gst.PadProbeType.BUFFER, rtp_probe)

    pipeline.set_state(Gst.State.PLAYING)

    loop = GLib.MainLoop()

    try:
        loop.run()
    except KeyboardInterrupt:
        print("\nStopping recording...")
        pipeline.set_state(Gst.State.NULL)
        loop.quit()


if __name__ == "__main__":
    main()