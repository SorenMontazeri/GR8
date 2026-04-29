from __future__ import annotations

import base64
import threading
from collections import deque
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import cv2
import gi
import numpy as np

from ingestion.buffers.rtsp_hot_buffer import BufferedFrame, FrameRingBuffer

gi.require_version("Gst", "1.0")
gi.require_version("GstRtp", "1.0")

from gi.repository import Gst, GstRtp, GLib


def add_onvif_replay_ext(rtsp_url: str) -> str:
    parsed = urlparse(rtsp_url)
    query = dict(parse_qsl(parsed.query))
    query["onvifreplayext"] = "1"
    return urlunparse(parsed._replace(query=urlencode(query)))


def ntp_to_datetime(ntp_seconds: int, ntp_fraction: int) -> datetime:
    unix_time = ntp_seconds - 2208988800 + ntp_fraction / (1 << 32)
    return datetime.fromtimestamp(unix_time, timezone.utc)


class GStreamerHotBuffer:
    def __init__(
        self,
        rtsp_url: str,
        camera_id: str,
        seconds: int = 30,
        fps: int = 5,
        max_bytes: int = 50 * 1024 * 1024,
        jpeg_quality: int = 70,
        max_width: int = 960,
    ) -> None:
        self.rtsp_url = add_onvif_replay_ext(rtsp_url)
        self.camera_id = str(camera_id)
        self.fps = fps
        self.jpeg_quality = jpeg_quality
        self.max_width = max_width

        self.buffer = FrameRingBuffer(
            max_frames=seconds * fps,
            max_bytes=max_bytes,
        )

        self._timestamps: deque[datetime] = deque(maxlen=300)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._loop: GLib.MainLoop | None = None
        self._pipeline: Gst.Pipeline | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run,
            name=f"camera-{self.camera_id}-gst-hot-buffer",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

        if self._pipeline is not None:
            self._pipeline.send_event(Gst.Event.new_eos())

        if self._loop is not None:
            self._loop.quit()

        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    def latest(self, seconds: int | None = None) -> list[BufferedFrame]:
        return self.buffer.latest(seconds)

    def frame_at(self, timestamp: datetime) -> BufferedFrame | None:
        return self.buffer.search_frame(timestamp)

    def stats(self) -> dict[str, int]:
        return self.buffer.stats()

    def _rtp_probe(self, pad, info):
        buf = info.get_buffer()
        if not buf:
            return Gst.PadProbeReturn.OK

        ok, rtp = GstRtp.RTPBuffer.map(buf, Gst.MapFlags.READ)
        if not ok:
            return Gst.PadProbeReturn.OK

        marker = GstRtp.RTPBuffer.get_marker(rtp)
        ext = GstRtp.RTPBuffer.get_extension_data(rtp)

        if marker and ext:
            ext_data, ext_id = ext

            if ext_id == 0xABAC:
                payload = ext_data.get_data()
                ntp_seconds = int.from_bytes(payload[0:4], "big")
                ntp_fraction = int.from_bytes(payload[4:8], "big")
                self._timestamps.append(ntp_to_datetime(ntp_seconds, ntp_fraction))

        GstRtp.RTPBuffer.unmap(rtp)
        return Gst.PadProbeReturn.OK

    def _on_sample(self, sink):
        sample = sink.emit("pull-sample")
        if sample is None or not self._timestamps:
            return Gst.FlowReturn.OK

        camera_time = self._timestamps.popleft()

        buf = sample.get_buffer()
        caps = sample.get_caps()
        info = caps.get_structure(0)

        width = info.get_value("width")
        height = info.get_value("height")

        ok, map_info = buf.map(Gst.MapFlags.READ)
        if not ok:
            return Gst.FlowReturn.OK

        frame = np.ndarray(
            shape=(height, width, 3),
            dtype=np.uint8,
            buffer=map_info.data,
        ).copy()

        buf.unmap(map_info)

        if self.max_width > 0 and width > self.max_width:
            new_height = int(height * (self.max_width / float(width)))
            frame = cv2.resize(frame, (self.max_width, new_height), interpolation=cv2.INTER_AREA)
            height, width = frame.shape[:2]

        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), int(self.jpeg_quality)]
        ok, encoded = cv2.imencode(".jpg", frame, encode_params)
        if not ok:
            return Gst.FlowReturn.OK

        self.buffer.append(
            BufferedFrame(
                timestamp=camera_time,
                jpeg_bytes=encoded.tobytes(),
                width=width,
                height=height,
            )
        )

        return Gst.FlowReturn.OK

    def _run(self) -> None:
        Gst.init(None)

        frame_interval = max(1, int(30 / self.fps))

        self._pipeline = Gst.parse_launch(
            f"""
            rtspsrc location="{self.rtsp_url}" protocols=tcp latency=100
            ! application/x-rtp,media=video,encoding-name=H264
            ! identity name=rtp_probe silent=true
            ! rtph264depay
            ! h264parse
            ! avdec_h264
            ! videoconvert
            ! video/x-raw,format=BGR
            ! videorate
            ! video/x-raw,framerate={self.fps}/1
            ! appsink name=sink emit-signals=true sync=false max-buffers=1 drop=true
            """
        )

        probe = self._pipeline.get_by_name("rtp_probe")
        probe.get_static_pad("src").add_probe(Gst.PadProbeType.BUFFER, self._rtp_probe)

        sink = self._pipeline.get_by_name("sink")
        sink.connect("new-sample", self._on_sample)

        self._loop = GLib.MainLoop()

        bus = self._pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message::eos", lambda *_: self._loop.quit())

        self._pipeline.set_state(Gst.State.PLAYING)
        self._loop.run()
        self._pipeline.set_state(Gst.State.NULL)