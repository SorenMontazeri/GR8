import csv
import os
import re
import signal
import time
import multiprocessing as mp
from collections import deque
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse


SEGMENT_NAME_RE = re.compile(r"^segment-(\d+)(?:_.*)?\.mp4$")


def add_onvif_replay_ext(rtsp_url):
    parsed = urlparse(rtsp_url)
    query = dict(parse_qsl(parsed.query))
    query["onvifreplayext"] = "1"
    return urlunparse(parsed._replace(query=urlencode(query)))


def next_segment_index(output_directory):
    highest = -1

    for name in os.listdir(output_directory):
        match = SEGMENT_NAME_RE.match(name)
        if match is not None:
            highest = max(highest, int(match.group(1)))

    return highest + 1


def build_informative_segment_name(index, camera_start_time):
    timestamp = camera_start_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    return f"segment-{index:05d}_{timestamp}.mp4"


def ntp_to_datetime(ntp_seconds, ntp_fraction):
    unix_time = ntp_seconds - 2208988800 + ntp_fraction / (1 << 32)
    return datetime.fromtimestamp(unix_time, timezone.utc)


def recorder_worker(rtsp_url, camera_id, segment_seconds, stop_event):
    import gi

    gi.require_version("Gst", "1.0")
    gi.require_version("GstRtp", "1.0")

    from gi.repository import Gst, GstRtp, GLib

    Gst.init(None)

    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    recordings_dir = os.path.join(root_dir, "recordings", str(camera_id))
    indexes_dir = os.path.join(root_dir, "indexes")

    os.makedirs(recordings_dir, exist_ok=True)
    os.makedirs(indexes_dir, exist_ok=True)

    index_path = os.path.join(indexes_dir, f"index-{camera_id}.csv")
    start_index = next_segment_index(recordings_dir)

    csv_exists = os.path.exists(index_path)

    csv_file = open(index_path, "a", newline="")
    writer = csv.writer(csv_file)

    if not csv_exists:
        writer.writerow(["file_name", "segment_start_camera_time", "segment_end_camera_time"])
        csv_file.flush()

    state = {
        "active_file": None,
        "segment_times": {},
        "written_files": set(),
        "stopping": False,
        "pts_to_camera_time": deque(maxlen=2000),
    }

    def final_file_name(file_name):
        if not file_name:
            return file_name

        times = state["segment_times"].get(file_name)
        if not times or not times["start"]:
            return file_name

        base_name = os.path.basename(file_name)
        match = SEGMENT_NAME_RE.match(base_name)
        if match is None:
            return file_name

        segment_index = int(match.group(1))
        target_name = build_informative_segment_name(segment_index, times["start"])
        target_path = os.path.join(os.path.dirname(file_name), target_name)

        if target_path == file_name:
            return file_name

        if not os.path.exists(target_path):
            os.replace(file_name, target_path)

        return target_path

    def write_index_row(file_name):
        if not file_name or file_name in state["written_files"]:
            return

        times = state["segment_times"].get(file_name)
        if not times or not times["start"] or not times["end"]:
            return

        renamed_path = final_file_name(file_name)

        writer.writerow([
            os.path.basename(renamed_path),
            times["start"].isoformat(),
            times["end"].isoformat(),
        ])
        csv_file.flush()
        state["written_files"].add(file_name)

    def on_splitmux_message(bus, message):
        structure = message.get_structure()
        if not structure:
            return

        name = structure.get_name()

        if name == "splitmuxsink-fragment-opened":
            file_name = structure.get_value("location")
            state["active_file"] = file_name
            state["segment_times"][file_name] = {"start": None, "end": None}

        elif name == "splitmuxsink-fragment-closed":
            file_name = structure.get_value("location")
            write_index_row(file_name)

    def rtp_probe(pad, info):
        buffer = info.get_buffer()
        if not buffer or buffer.pts == Gst.CLOCK_TIME_NONE:
            return Gst.PadProbeReturn.OK

        ok, rtp = GstRtp.RTPBuffer.map(buffer, Gst.MapFlags.READ)
        if not ok:
            return Gst.PadProbeReturn.OK

        marker = GstRtp.RTPBuffer.get_marker(rtp)
        ext = GstRtp.RTPBuffer.get_extension_data(rtp)

        if ext and marker:
            ext_data, ext_id = ext

            if ext_id == 0xABAC:
                payload = ext_data.get_data()

                ntp_seconds = int.from_bytes(payload[0:4], "big")
                ntp_fraction = int.from_bytes(payload[4:8], "big")
                camera_time = ntp_to_datetime(ntp_seconds, ntp_fraction)
                state["pts_to_camera_time"].append((buffer.pts, camera_time))

        GstRtp.RTPBuffer.unmap(rtp)
        return Gst.PadProbeReturn.OK

    def camera_time_for_pts(pts):
        if not state["pts_to_camera_time"]:
            return None

        closest_pts, camera_time = min(
            state["pts_to_camera_time"],
            key=lambda item: abs(item[0] - pts),
        )

        if abs(closest_pts - pts) > 100 * Gst.MSECOND:
            return None

        return camera_time

    def parsed_video_probe(pad, info):
        buffer = info.get_buffer()
        if not buffer or buffer.pts == Gst.CLOCK_TIME_NONE:
            return Gst.PadProbeReturn.OK

        if not state["active_file"]:
            return Gst.PadProbeReturn.OK

        camera_time = camera_time_for_pts(buffer.pts)
        if camera_time is None:
            return Gst.PadProbeReturn.OK

        times = state["segment_times"][state["active_file"]]

        if times["start"] is None:
            times["start"] = camera_time

        times["end"] = camera_time

        return Gst.PadProbeReturn.OK

    pipeline = Gst.parse_launch(
        f"""
        rtspsrc location="{add_onvif_replay_ext(rtsp_url)}" protocols=tcp latency=100
        ! application/x-rtp,media=video,encoding-name=H264
        ! identity name=rtp_probe silent=true
        ! rtph264depay
        ! h264parse config-interval=-1
        ! identity name=parsed_video_probe silent=true
        ! splitmuxsink
            name=mux
            location="{recordings_dir}/segment-%05d.mp4"
            muxer-factory=mp4mux
            max-size-time={segment_seconds * 1_000_000_000}
            start-index={start_index}
        """
    )

    probe = pipeline.get_by_name("rtp_probe")
    probe.get_static_pad("src").add_probe(Gst.PadProbeType.BUFFER, rtp_probe)

    parsed_probe = pipeline.get_by_name("parsed_video_probe")
    parsed_probe.get_static_pad("src").add_probe(
        Gst.PadProbeType.BUFFER,
        parsed_video_probe,
    )

    loop = GLib.MainLoop()

    def request_shutdown():
        if stop_event.is_set() and not state["stopping"]:
            state["stopping"] = True
            pipeline.send_event(Gst.Event.new_eos())
            return False

        return True

    def on_bus_message(bus, message):
        if message.type == Gst.MessageType.ELEMENT:
            on_splitmux_message(bus, message)

        elif message.type == Gst.MessageType.EOS:
            write_index_row(state["active_file"])
            loop.quit()

    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect("message", on_bus_message)

    def signal_shutdown(signum, frame):
        stop_event.set()

    signal.signal(signal.SIGTERM, signal_shutdown)
    signal.signal(signal.SIGINT, signal_shutdown)

    GLib.timeout_add(200, request_shutdown)

    pipeline.set_state(Gst.State.PLAYING)
    loop.run()

    write_index_row(state["active_file"])
    pipeline.set_state(Gst.State.NULL)
    csv_file.close()


class GStreamerRecorder:
    def __init__(self, rtsp_url, camera_id, segment_seconds=10):
        self.rtsp_url = rtsp_url
        self.camera_id = str(camera_id)
        self.segment_seconds = segment_seconds
        self.stop_event = mp.Event()
        self.process = None

    def start(self):
        self.process = mp.Process(
            target=recorder_worker,
            args=(self.rtsp_url, self.camera_id, self.segment_seconds, self.stop_event),
            daemon=False,
        )
        self.process.start()
        return self.process

    def stop(self):
        if self.process and self.process.is_alive():
            self.stop_event.set()
            self.process.join(timeout=15)

            if self.process.is_alive():
                self.process.terminate()
                self.process.join(timeout=5)

            if self.process.is_alive():
                self.process.kill()
                self.process.join()


if __name__ == "__main__":
    camera_ip = "192.168.0.90"
    username = "student"
    password = "student"
    camera_id = "1"

    rtsp_url = f"rtsp://{username}:{password}@{camera_ip}/axis-media/media.amp"

    recorder = GStreamerRecorder(
        rtsp_url=rtsp_url,
        camera_id=camera_id,
        segment_seconds=10,
    )

    recorder.start()
    count = 0

    try:
        while True:
            time.sleep(1)
            print(count)
            count += 1
    except KeyboardInterrupt:
        recorder.stop()
