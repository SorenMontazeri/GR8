from __future__ import annotations
import base64
import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import os
import asyncio
import numpy as np
from ingestion.source.replay_reader import RawEvent
from ingestion.storage.raw_event_store import RawEventStore

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - optional in thin test envs
    def load_dotenv() -> bool:
        return False


import cv2
import paho.mqtt.client as mqtt

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.database import save_description_bundle
from ingestion.buffers.mqtt_event_buffer import BufferedMqttEvent, MqttEventRingBuffer
from ingestion.buffers.rtsp_hot_buffer import BufferedFrame
from ingestion.gstreamer_recorder import GStreamerRecorder

class Camera:
    def __init__(
        self,
        camera_id: str,
        rtsp_url: str,
        broker_host: str,
        broker_port: int,
        analysis_client=None,
        segment_seconds: int = 10,
        hot_buffer_seconds: int = 30,
        hot_buffer_fps: int = 5,
        hot_buffer_max_bytes: int = 50 * 1024 * 1024, #TODO increase max bytes if needed
        mqtt_buffer_max_events: int = 300,
        mqtt_buffer_max_bytes: int = 5 * 1024 * 1024,
        hot_buffer_jpeg_quality: int = 70,
        hot_buffer_max_width: int = 960,
        frame_match_tolerance_ms: int = 500,
        enable_recording: bool = True,
        use_onvif_replay_ext: bool = True,
        hot_buffer_backend: str = "opencv",
        raw_events_output_path: str | None = None,
    ) -> None:
        
        """
        Initializes a Camera instance.

        Sets up:
        - RTSP connection and camera identifier
        - MQTT client and event buffer
        - Hot buffer for video frames
        - Async event loop in a separate thread
        - Thread pool for analysis tasks
        - Recording (optional)
        - Raw event storage to file

        Acts as the main pipeline:
        ingest → buffer → analysis → storage.
        """
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.recorder: GStreamerRecorder | None = None
        self.mqtt_client = mqtt.Client()
        if raw_events_output_path is None:
            session_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            raw_events_output_path = str(
                Path(__file__).resolve().parent.parent
                / "replay_out"
                / "live"
                / f"camera_{self.camera_id}_{session_stamp}.jsonl"
            )
        self.raw_events_output_path = raw_events_output_path
        self.raw_event_store = RawEventStore(output_path=self.raw_events_output_path)

        self.hot_buffer: Any | None = None
        self.mqtt_buffer = MqttEventRingBuffer(
            max_events=mqtt_buffer_max_events,
            max_bytes=mqtt_buffer_max_bytes,
        )
        self.analysis_client = analysis_client
        self.frame_match_tolerance_ms = frame_match_tolerance_ms
        self._analysis_pool = ThreadPoolExecutor(
            max_workers=10,
            thread_name_prefix=f"camera-{self.camera_id}-analysis",
        )

        # Fix for asyncio
        self._async_loop = asyncio.new_event_loop()
        self._async_thread: threading.Thread | None = None
        self._async_loop_ready = threading.Event()
        self.init_async_loop()

        if enable_recording:
            self.init_recording(segment_seconds)
        self.init_buffer(
            seconds=hot_buffer_seconds,
            fps=hot_buffer_fps,
            max_bytes=hot_buffer_max_bytes,
            jpeg_quality=hot_buffer_jpeg_quality,
            max_width=hot_buffer_max_width,
            use_onvif_replay_ext=use_onvif_replay_ext,
            backend=hot_buffer_backend,
        )
        self.init_mqtt(broker_host, broker_port)

    def init_recording(self, segment_seconds: int) -> None:
        """
        Starts video recording using GStreamer.

        Splits the recording into segments of the given duration (seconds).
        """
        self.recorder = GStreamerRecorder(
            rtsp_url=self.rtsp_url,
            camera_id=self.camera_id,
            segment_seconds=segment_seconds,
        )
        self.recorder.start()

    def init_mqtt(self, broker_host: str, broker_port: int) -> None:
        """
        Initializes MQTT connection:
        - Connects to broker
        - Sets message callback (on_message)
        - Subscribes to the camera topic
        - Starts background loop
        """
        self.mqtt_client.connect(broker_host, broker_port, 60)
        self.mqtt_client.on_message = self.on_message
        self.mqtt_client.subscribe(f"camera/{self.camera_id}")
        self.mqtt_client.loop_start()

    def init_async_loop(self) -> None:
        """
        Starts a separate thread running an asyncio event loop.

        Required to run async analysis tasks without blocking the main thread.
        """
        self._async_thread = threading.Thread(
            target=self._async_loop_thread_main,
            name=f"camera-{self.camera_id}-async-loop",
            daemon=True,
        )
        self._async_thread.start()

        if not self._async_loop_ready.wait(timeout=5.0):
            raise RuntimeError(f"[camera:{self.camera_id}] async loop failed to start")

    def _async_loop_thread_main(self) -> None:
        """
        Entry point for the async thread:
        - Sets the event loop
        - Signals that the loop is ready
        - Runs the loop indefinitely
        """
        asyncio.set_event_loop(self._async_loop)
        self._async_loop_ready.set()
        self._async_loop.run_forever()

    async def _run_analysis(
        self,
        snapshot_b64: str,
        full_frame_b64: str | None,
        selection_1_images: list[str],
        selection_2_images: list[str],
    ) -> tuple[Any, Any, Any, Any]:
        
        """
        Runs multiple analysis queries in parallel via the analysis client.

        Returns:
        - Snapshot description
        - Full frame description
        - Selection 1 description
        - Selection 2 description
        """
        return await asyncio.gather(
            self.analysis_client.query_description_open([snapshot_b64]),
            self.analysis_client.query_description_open([full_frame_b64]),
            self.analysis_client.query_description_open(selection_1_images),
            self.analysis_client.query_description_open(selection_2_images),
        )

    def on_message(self, client, userdata, msg) -> None:
        """
        Callback for incoming MQTT messages.

        Performs:
        - JSON parsing of payload
        - Stores raw event data
        - Submits processing to thread pool (_process_message)
        """
        try:
            payload = msg.payload.decode("utf-8", errors="replace")
            data = json.loads(payload)
        except Exception as e:
            print(f"[camera:{self.camera_id}][mqtt] invalid json: {e}")
            return
        if not isinstance(data, dict):
            print(f"[camera:{self.camera_id}][mqtt] payload is not a JSON object")
            return

        print(f"[camera:{self.camera_id}][mqtt] received message")
        received_at = datetime.now(timezone.utc)
        try:
            self.raw_event_store.append(
                RawEvent(
                    raw=data,
                    received_at=received_at,
                    source="live",
                )
            )
        except Exception as exc:
            print(f"[camera:{self.camera_id}][mqtt] raw event store append failed: {exc}")
        self._analysis_pool.submit(self._process_message, data)

    def _process_message(self, data: Dict[str, Any]) -> None:
        """
        Main logic for processing an MQTT event.

        Steps:
        1. Extract start/end timestamps
        2. Retrieve snapshot image
        3. Match snapshot with full frame from hot buffer
        4. Select frame sequences (two strategies)
        5. Run AI analysis asynchronously
        6. Save results to database
        """
        try:
            # Get necessary info
            package_start_time = self._extract_event_timestamp(data)
            package_end_time = self._extract_event_end_time(data)
            if package_start_time is None or package_end_time is None:
                print(f"[camera:{self.camera_id}] missing mqtt timestamps")
                return

            target_start_time = package_start_time
            target_end_time = package_end_time

            image = data.get("image")
            snapshot_b64 = image.get("data") if isinstance(image, dict) else None
            if snapshot_b64 is None:
                print(f"[camera:{self.camera_id}] missing mqtt snapshot")
                return
            snapshot_timestamp = self._extract_image_timestamp(image if isinstance(image, dict) else None)
            if snapshot_timestamp is None:
                snapshot_timestamp = target_end_time

            match_target_time, matched_full_frame = self._match_full_frame(
                image=image if isinstance(image, dict) else None,
                start_time=target_start_time,
                end_time=target_end_time,
            )
            if matched_full_frame is None:
                print(
                    f"[camera:{self.camera_id}] no matching frame in hot buffer "
                    f"(tolerance_ms={self.frame_match_tolerance_ms})"
                )
                full_frame_b64 = None
                full_frame_timestamp = None
            else:
                full_frame_b64 = base64.b64encode(matched_full_frame.jpeg_bytes).decode("utf-8")
                full_frame_timestamp = matched_full_frame.timestamp
                delta_ms = int(abs((matched_full_frame.timestamp - match_target_time).total_seconds()) * 1000)
                print(
                    f"[camera:{self.camera_id}] full-frame match delta_ms={delta_ms} "
                    f"target={match_target_time.isoformat()} matched={matched_full_frame.timestamp.isoformat()}"
                )

            selection_1_images, selection_1_timestamps =  self.frame_selection_1(target_start_time, target_end_time)
            selection_2_images, selection_2_timestamps =  self.frame_selection_2(target_start_time, target_end_time, 90)


            try:
                future = asyncio.run_coroutine_threadsafe(
                    self._run_analysis(
                        snapshot_b64=snapshot_b64,
                        full_frame_b64=full_frame_b64,
                        selection_1_images=selection_1_images,
                        selection_2_images=selection_2_images,
                    ),
                    self._async_loop,
                )
                analysis_results = future.result(timeout=60)

            except Exception as exc:
                print(f"[camera:{self.camera_id}] analysis failed: {exc}")
                return

            response_snapshot = analysis_results["snapshot"]
            response_full_frame = analysis_results.get("full_frame")
            response_selection_1 = analysis_results.get("uniform")
            response_selection_2 = analysis_results.get("varied")

            print(response_snapshot)
            if response_full_frame is not None:
                print(response_full_frame)
            if response_selection_1 is not None:
                print(response_selection_1)
            if response_selection_2 is not None:
                print(response_selection_2)

            try:
                save_description_bundle(
                    timestamp_start=target_start_time,
                    timestamp_end=target_end_time,
                    created_at=datetime.now(timezone.utc),
                    uniform_llm_description=response_selection_1["description"] if response_selection_1 is not None else None,
                    varied_llm_description=response_selection_2["description"] if response_selection_2 is not None else None,
                    snapshot_llm_description=response_snapshot["description"],
                    full_frame_llm_description=response_full_frame["description"] if response_full_frame is not None else None,
                    uniform_timestamps=selection_1_timestamps if response_selection_1 is not None else None,
                    varied_timestamps=selection_2_timestamps if response_selection_2 is not None else None,
                    snapshot_timestamp=snapshot_timestamp,
                    full_frame_timestamp=full_frame_timestamp,
                    snapshot_image_base64=snapshot_b64,
                    full_frame_image_base64=full_frame_b64,
                    uniform_images_base64=selection_1_images if response_selection_1 is not None else None,
                    varied_images_base64=selection_2_images if response_selection_2 is not None else None,
                )
            except Exception as exc:
                print(f"[camera:{self.camera_id}] saving to database failed: {exc}")
        except Exception as exc:
            print(f"[camera:{self.camera_id}] unexpected processing error: {exc}")
            traceback.print_exc()


    def _extract_event_timestamp(self, payload: Dict[str, Any]) -> datetime | None:
        """
        Extracts and parses 'start_time' from MQTT payload.

        Returns UTC datetime or None on failure.
        """

        start_time = payload.get("start_time")
        if isinstance(start_time, str) and start_time.strip():
            try:
                parsed = datetime.fromisoformat(start_time.strip().replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc)
            except ValueError:
                print(f"[camera:{self.camera_id}][mqtt] invalid start_time format: {start_time}")

        return None
    
    def _extract_event_end_time(self, payload: Dict[str, Any]) -> datetime | None:
        """
        Extracts and parses 'end_time' from MQTT payload.

        Returns UTC datetime or None on failure.
        """

        end_time = payload.get("end_time")
        if isinstance(end_time, str) and end_time.strip():
            try:
                parsed = datetime.fromisoformat(end_time.strip().replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc)
            except ValueError:
                print(f"[camera:{self.camera_id}][mqtt] invalid start_time format: {end_time}")

        return None

    def _extract_image_timestamp(self, image_payload: Dict[str, Any] | None) -> datetime | None:
        """
        Extracts timestamp from image metadata.

        Tries multiple keys:
        - timestamp
        - time
        - created_at
        """

        if not isinstance(image_payload, dict):
            return None

        for key in ("timestamp", "time", "created_at"):
            value = image_payload.get(key)
            if isinstance(value, str) and value.strip():
                try:
                    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    return parsed.astimezone(timezone.utc)
                except ValueError:
                    print(f"[camera:{self.camera_id}][mqtt] invalid {key} format: {value}")

        return None

    def _frame_match_candidates(
        self,
        image_payload: Dict[str, Any] | None,
        start_time: datetime,
        end_time: datetime,
    ) -> list[datetime]:
        """
        Generates candidate timestamps for frame matching.

        Includes:
        - Image timestamp
        - Interval midpoint
        - Start time
        - End time
        """

        candidates: list[datetime] = []
        image_time = self._extract_image_timestamp(image_payload)
        midpoint = start_time + ((end_time - start_time) / 2)

        for candidate in (image_time, midpoint, end_time, start_time):
            if candidate is None:
                continue
            if candidate not in candidates:
                candidates.append(candidate)

        return candidates

    def _match_full_frame(
        self,
        image: Dict[str, Any] | None,
        start_time: datetime,
        end_time: datetime,
    ) -> tuple[datetime, BufferedFrame | None]:
        """
        Attempts to find a matching frame in the hot buffer.

        Tries multiple candidate timestamps and returns:
        - Best matching timestamp
        - Corresponding frame (or None)
        """

        for candidate in self._frame_match_candidates(image, start_time, end_time):
            frame = self.get_hot_buffer_frame_at(candidate, tolerance_ms=self.frame_match_tolerance_ms)
            if frame is not None:
                return candidate, frame

        return end_time, None

    def init_buffer(
        self,
        seconds: int,
        fps: int,
        max_bytes: int,
        jpeg_quality: int,
        max_width: int,
        use_onvif_replay_ext: bool,
        backend: str,
    ) -> None:
        """
        Initializes the hot buffer for video frames.

        Supports two backends:
        - GStreamer
        - OpenCV

        Starts the buffer immediately.
        """

        if backend == "gstreamer":
            from ingestion.gstreamer_hot_buffer import GStreamerHotBuffer

            self.hot_buffer = GStreamerHotBuffer(
                rtsp_url=self.rtsp_url,
                camera_id=self.camera_id,
                seconds=seconds,
                fps=fps,
                max_bytes=max_bytes,
                jpeg_quality=jpeg_quality,
                max_width=max_width,
                use_onvif_replay_ext=use_onvif_replay_ext,
            )
        elif backend == "opencv":
            from ingestion.opencv_hot_buffer import OpenCvHotBuffer

            self.hot_buffer = OpenCvHotBuffer(
                rtsp_url=self.rtsp_url,
                camera_id=self.camera_id,
                seconds=seconds,
                fps=fps,
                max_bytes=max_bytes,
                jpeg_quality=jpeg_quality,
                max_width=max_width,
            )
        else:
            raise ValueError(f"Unsupported hot buffer backend: {backend}")

        self.hot_buffer.start()

    def get_hot_buffer_frames(self, seconds: int | None = None) -> List[BufferedFrame]:
        """
        Returns recent frames from the hot buffer.

        Can optionally limit by time range (seconds).
        """

        if self.hot_buffer is None:
            return []
        return self.hot_buffer.latest(seconds)

    def get_hot_buffer_frame_at(
        self,
        target_timestamp: datetime,
        tolerance_ms: int | None = None,
    ) -> BufferedFrame | None:
        """
        Retrieves a frame closest to a given timestamp.

        If tolerance is provided:
        - Returns None if the frame is too far in time
        """

        if self.hot_buffer is None:
            return None
        frame = self.hot_buffer.frame_at(target_timestamp)
        if frame is None or tolerance_ms is None:
            return frame

        delta_ms = abs((frame.timestamp - target_timestamp).total_seconds()) * 1000.0
        if delta_ms > tolerance_ms:
            return None
        return frame

    def get_mqtt_event_at(
        self,
        target_timestamp: datetime,
        tolerance_ms: Optional[int] = None,
    ) -> Optional[BufferedMqttEvent]:
        """
        Retrieves an MQTT event near a given timestamp.
        """

        return self.mqtt_buffer.search_event(target_timestamp, tolerance_ms=tolerance_ms)

    def get_context_at(
        self,
        target_timestamp: datetime,
        tolerance_ms: Optional[int] = 500,
    ) -> Dict[str, Any]:
        """
        Returns combined context:
        - Frame
        - MQTT event
        - Whether each was found

        Useful for debugging and analysis.
        """

        frame = self.get_hot_buffer_frame_at(target_timestamp)
        mqtt_event = self.get_mqtt_event_at(target_timestamp, tolerance_ms=tolerance_ms)
        return {
            "target_timestamp": target_timestamp,
            "frame": frame,
            "mqtt_event": mqtt_event,
            "frame_found": frame is not None,
            "mqtt_found": mqtt_event is not None,
        }

    def frame_selection_1(self, start_time: datetime, end_time: datetime) -> tuple[list[str], list[datetime]]:
        """
        Simple uniform sampling of frames across a time range.

        - Selects evenly spaced frames
        - Avoids duplicates
        - Returns base64-encoded images and timestamps
        """

        if end_time < start_time:
            return [], []

        def encode_frame(frame: BufferedFrame) -> str:
            return base64.b64encode(frame.jpeg_bytes).decode("utf-8")

        if self.hot_buffer is None:
            return [], []

        duration = (end_time - start_time).total_seconds()
        frame_count = 1 if duration <= 1 else min(int(duration), max(5, int(duration / 3)))

        if frame_count <= 0:
            return [], []

        selected_frames: list[str] = []
        selected_timestamps: list[datetime] = []
        seen: set[bytes] = set()
        step = timedelta(0) if frame_count == 1 else (end_time - start_time) / (frame_count - 1)

        for i in range(frame_count):
            frame = self.get_hot_buffer_frame_at(
                start_time + step * i,
                tolerance_ms=self.frame_match_tolerance_ms,
            )
            if frame is None or frame.timestamp < start_time or frame.timestamp > end_time:
                continue
            if frame.jpeg_bytes in seen:
                continue
            seen.add(frame.jpeg_bytes)
            selected_frames.append(encode_frame(frame))
            selected_timestamps.append(frame.timestamp)

        return selected_frames, selected_timestamps
    
    def frame_selection_2(self, start_time: datetime, end_time: datetime, max_change_percent: float, max_interval_seconds: int = 10) -> tuple[list[str], list[datetime]]:
        """
        Advanced frame selection based on visual changes.

        - Uses image difference (OpenCV)
        - Skips frames with minimal change
        - Limits maximum time gap between selected frames

        Useful for obtaining meaningful frames instead of uniform sampling.
        """

        if end_time < start_time or max_change_percent < 0 or max_interval_seconds <= 0:
            return [], []

        def thumbnail(frame: BufferedFrame):
            image = cv2.imdecode(np.frombuffer(frame.jpeg_bytes, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
            resized_image = cv2.resize(image, (max(1, frame.width // 8), max(1, frame.height // 8)), interpolation=cv2.INTER_AREA)
            return cv2.GaussianBlur(resized_image, (3, 3), 0)

        def changed_pixel_ratio(left, right) -> float:
            pixel_threshold = 12
            diff = cv2.absdiff(left, right)
            return float((diff > pixel_threshold).sum()) * 100.0 / float(diff.size)

        def encode_frame(frame: BufferedFrame) -> str:
            return base64.b64encode(frame.jpeg_bytes).decode("utf-8")

        if self.hot_buffer is None:
            return [], []

        buffer_frames = self.hot_buffer.frames_between(start_time, end_time)

        if not buffer_frames:
            return [], []

        selected_frames = [encode_frame(buffer_frames[0])]
        selected_timestamps = [buffer_frames[0].timestamp]
        current_frame = buffer_frames[0]
        
        for next_frame in buffer_frames[1:]:
            change_percent = changed_pixel_ratio(thumbnail(current_frame), thumbnail(next_frame))
            if change_percent > max_change_percent and next_frame.timestamp < current_frame.timestamp + timedelta(seconds=max_interval_seconds):
                continue

            selected_frames.append(encode_frame(next_frame))
            selected_timestamps.append(next_frame.timestamp)
            current_frame = next_frame

        return selected_frames, selected_timestamps

    def hot_buffer_stats(self) -> Dict[str, int]:
        """
        Returns statistics for the hot buffer:
        - Number of frames
        - Memory usage (bytes)
        - Maximum limits
        """

        if self.hot_buffer is None:
            return {"frames": 0, "bytes": 0, "max_frames": 0, "max_bytes": 0}
        return self.hot_buffer.stats()

    def mqtt_buffer_stats(self) -> Dict[str, int]:
        """
        Returns statistics for the MQTT buffer:
        - Number of events
        - Memory usage
        """

        return self.mqtt_buffer.stats()

    def dump_latest_hot_buffer_frame(self, output_path: str = "debug_latest.jpg") -> bool:
        """
        Saves the most recent frame from the hot buffer to disk.

        Useful for debugging the video stream.
        """

        frames = self.get_hot_buffer_frames(5)
        if not frames:
            print(f"[camera:{self.camera_id}][buffer] no frames to dump")
            return False

        latest = frames[-1]
        with open(output_path, "wb") as f:
            f.write(latest.jpeg_bytes)

        print(
            f"[camera:{self.camera_id}][buffer] wrote {output_path} "
            f"ts={latest.timestamp.isoformat()} size={latest.width}x{latest.height} "
            f"bytes={len(latest.jpeg_bytes)}"
        )
        return True

    def stop_recording(self) -> None:
        """
        Stops all running components:
        - Hot buffer
        - MQTT client
        - Thread pool
        - Video recording

        Should always be called on shutdown.
        """

        if self.hot_buffer is not None:
            self.hot_buffer.stop()
            self.hot_buffer = None

        self.mqtt_client.loop_stop()
        self.mqtt_client.disconnect()
        self._analysis_pool.shutdown(wait=True)

        if self.recorder is not None:
            self.recorder.stop()
            self.recorder = None


def main() -> None:
    from analysis.async_prisma import LLMClient

    load_dotenv()
    camera_ip = "192.168.0.90"
    username = "student"
    password = "student"
    rtsp_url = f"rtsp://{username}:{password}@{camera_ip}/axis-media/media.amp"

    broker_host = "10.255.255.1"
    broker_port = 1883
    
    endpoint = "https://api.ai.auth.axis.cloud/v1/chat/completions"
    api_key = os.environ.get("FACADE_API_KEY")
    model = "prisma_gemini_pro"

    llm = LLMClient(endpoint, api_key, model)

    camera = Camera(
        "1",
        rtsp_url,
        broker_host,
        broker_port,
        analysis_client=llm,
        segment_seconds=10,
        hot_buffer_backend="gstreamer",
    )
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        camera.stop_recording()


if __name__ == "__main__":
    main()
