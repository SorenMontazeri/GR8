import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import imageio_ffmpeg

RECORDINGS_ROOT = Path(__file__).resolve().parent.parent / "database" / "recordings"


def _recordings_directory(camera_id: str | int) -> Path:
    camera_id = str(camera_id)
    output_directory = RECORDINGS_ROOT / camera_id
    output_directory.mkdir(parents=True, exist_ok=True)
    return output_directory


def record_once(ffmpeg, rtsp_url, camera_id, duration_seconds):
    # setup directory
    output_directory = _recordings_directory(camera_id)

    # single output file (UTC timestamp)
    now = datetime.now(timezone.utc)
    file_name = f"D{now.strftime('%Y-%m-%d-T%H-%M-%S')}.mp4"
    output_file = str(output_directory / file_name)

    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel", "warning",

        "-rtsp_transport", "tcp",
        "-i", rtsp_url,

        "-an",              # Drop audio
        "-c", "copy",       # Stream copy (no decode/encode)

        "-t", str(duration_seconds),
        "-movflags", "+faststart",

        output_file,
    ]

    subprocess.run(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )

def start_recording_ffmpeg(ffmpeg, rtsp_url, camera_id, segment_seconds=10): # Will create a seperate process, pls be careful

    # setup directory
    output_directory = _recordings_directory(camera_id)
    file = str(output_directory / "D%Y-%m-%d-T%H-%M-%S.mp4")

    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel", "warning",

        "-rtsp_transport", "tcp",
        "-i", rtsp_url,

        "-an",              # Drop audio
        "-c", "copy",       # Stream copy (no decode/encode)

        "-f", "segment",
        "-segment_time", str(segment_seconds),
        "-reset_timestamps", "1",
        "-strftime", "1",
        "-movflags", "+faststart",

        file,
    ]

    return subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def stop_recording(process):
    if process is None:
        return
    process.terminate()


def main():
    camera_ip = "192.168.0.90"
    username = "student"
    password = "student"
    rtsp_url = f"rtsp://{username}:{password}@{camera_ip}/axis-media/media.amp"
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    start_recording_ffmpeg(ffmpeg, rtsp_url, 1, 10)


if __name__ == "__main__":
    main()
