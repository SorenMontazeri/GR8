from __future__ import annotations

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
        self.seconds = seconds
        self.fps = fps
        self.jpeg_quality = jpeg_quality
        self.max_width = max_width

        self._buffer = FrameRingBuffer(
            max_frames=seconds * fps,
            max_bytes=max_bytes,
        )

        self._pts_to_camera_time: deque[tuple[int, datetime]] = deque(maxlen=1000)
        self._pts_lock = threading.Lock()

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
        if self._pipeline is not None:
            self._pipeline.send_event(Gst.Event.new_eos())

        if self._loop is not None:
            self._loop.quit()

        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    def latest(self, seconds: int | None = None) -> list[BufferedFrame]:
        window = seconds if seconds is not None else self.seconds
        return self._buffer.latest(window)

    def frame_at(self, timestamp: datetime) -> BufferedFrame | None:
        return self._buffer.frame_at(timestamp)

    def frames_between(self, start_time: datetime, end_time: datetime) -> list[BufferedFrame]:
        return self._buffer.frames_between(start_time, end_time)

    def stats(self) -> dict[str, int]:
        return self._buffer.stats()

    def _rtp_probe(self, pad, info):
        buf = info.get_buffer()
        if not buf:
            return Gst.PadProbeReturn.OK

        ok, rtp = GstRtp.RTPBuffer.map(buf, Gst.MapFlags.READ)
        if not ok:
            return Gst.PadProbeReturn.OK

        marker = GstRtp.RTPBuffer.get_marker(rtp)
        ext = GstRtp.RTPBuffer.get_extension_data(rtp)

        if marker and ext and buf.pts != Gst.CLOCK_TIME_NONE:
            ext_data, ext_id = ext

            if ext_id == 0xABAC:
                payload = ext_data.get_data()
                ntp_seconds = int.from_bytes(payload[0:4], "big")
                ntp_fraction = int.from_bytes(payload[4:8], "big")
                camera_time = ntp_to_datetime(ntp_seconds, ntp_fraction)

                with self._pts_lock:
                    self._pts_to_camera_time.append((buf.pts, camera_time))

        GstRtp.RTPBuffer.unmap(rtp)
        return Gst.PadProbeReturn.OK

    def _camera_time_for_pts(self, pts: int) -> datetime | None:
        with self._pts_lock:
            if not self._pts_to_camera_time:
                return None

            closest_pts, closest_time = min(
                self._pts_to_camera_time,
                key=lambda item: abs(item[0] - pts),
            )

            if abs(closest_pts - pts) > Gst.SECOND:
                return None

            return closest_time

    def _on_sample(self, sink):
        sample = sink.emit("pull-sample")
        if sample is None:
            return Gst.FlowReturn.OK

        buf = sample.get_buffer()
        if buf.pts == Gst.CLOCK_TIME_NONE:
            return Gst.FlowReturn.OK

        camera_time = self._camera_time_for_pts(buf.pts)
        if camera_time is None:
            return Gst.FlowReturn.OK

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
            frame = cv2.resize(
                frame,
                (self.max_width, new_height),
                interpolation=cv2.INTER_AREA,
            )
            height, width = frame.shape[:2]

        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), int(self.jpeg_quality)]
        ok, encoded = cv2.imencode(".jpg", frame, encode_params)
        if not ok:
            return Gst.FlowReturn.OK

        self._buffer.append(
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