from __future__ import annotations

import subprocess
from pathlib import Path


class RtspStreamer:
    def __init__(
        self,
        *,
        ffmpeg_path: str,
        video_path: str | Path,
        publish_url: str,
        loop_forever: bool = False,
    ) -> None:
        self.ffmpeg_path = ffmpeg_path
        self.video_path = str(video_path)
        self.publish_url = publish_url
        self.loop_forever = loop_forever
        self.process: subprocess.Popen[str] | None = None

    def build_command(self) -> list[str]:
        stream_loop_value = "-1" if self.loop_forever else "0"
        return [
            self.ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "warning",
            "-re",
            "-stream_loop",
            stream_loop_value,
            "-i",
            self.video_path,
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-tune",
            "zerolatency",
            "-g",
            "10",
            "-keyint_min",
            "10",
            "-bf",
            "0",
            "-pix_fmt",
            "yuv420p",
            "-f",
            "rtsp",
            "-rtsp_transport",
            "tcp",
            self.publish_url,
        ]

    def start(self) -> subprocess.Popen[str]:
        if self.process is not None:
            raise RuntimeError("RTSP streamer already started.")
        self.process = subprocess.Popen(
            self.build_command(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return self.process

    def wait(self) -> int:
        if self.process is None:
            raise RuntimeError("RTSP streamer is not running.")
        return self.process.wait()

    def stop(self) -> None:
        if self.process is None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        finally:
            self.process = None
