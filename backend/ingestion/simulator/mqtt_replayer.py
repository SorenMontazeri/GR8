from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from typing import Protocol

try:
    import paho.mqtt.client as mqtt
except ModuleNotFoundError:  # pragma: no cover - tests can inject fake client
    mqtt = None

from ingestion.simulator.scenario_loader import Scenario
from ingestion.simulator.timestamp_rewriter import rewrite_payload_timestamps


class _PublisherClient(Protocol):
    def connect(self, host: str, port: int, keepalive: int) -> None: ...
    def loop_start(self) -> None: ...
    def loop_stop(self) -> None: ...
    def disconnect(self) -> None: ...
    def publish(self, topic: str, payload: str) -> object: ...


class MqttReplayer:
    def __init__(
        self,
        *,
        scenario: Scenario,
        camera_id: str,
        broker_host: str,
        broker_port: int,
        topic_prefix: str = "camera",
        client: _PublisherClient | None = None,
        sleep_fn=time.sleep,
        monotonic_fn=time.monotonic,
    ) -> None:
        self.scenario = scenario
        self.camera_id = str(camera_id)
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.topic = f"{topic_prefix}/{self.camera_id}"
        if client is not None:
            self.client = client
        else:
            if mqtt is None:
                raise ModuleNotFoundError("paho-mqtt is required unless a client is injected.")
            self.client = mqtt.Client()
        self.sleep_fn = sleep_fn
        self.monotonic_fn = monotonic_fn
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def stopped(self) -> bool:
        return self._stop_event.is_set()

    def run(self, simulation_start_wallclock_utc: datetime) -> int:
        if simulation_start_wallclock_utc.tzinfo is None:
            raise ValueError("simulation_start_wallclock_utc must be timezone-aware.")

        published = 0
        monotonic_start = self.monotonic_fn()
        self.client.connect(self.broker_host, self.broker_port, 60)
        self.client.loop_start()
        try:
            for event in self.scenario.events:
                if self._stop_event.is_set():
                    break

                self._wait_until_offset(monotonic_start, event.offset_ms)
                if self._stop_event.is_set():
                    break

                payload = rewrite_payload_timestamps(
                    event.payload,
                    original_event_timestamp=event.original_timestamp,
                    simulation_start_wallclock_utc=simulation_start_wallclock_utc,
                    offset_ms=event.offset_ms,
                )
                self.client.publish(self.topic, json.dumps(payload))
                published += 1
        finally:
            self.client.loop_stop()
            self.client.disconnect()
        return published

    def _wait_until_offset(self, monotonic_start: float, offset_ms: int) -> None:
        target = monotonic_start + (offset_ms / 1000.0)
        while not self._stop_event.is_set():
            remaining = target - self.monotonic_fn()
            if remaining <= 0:
                return
            self.sleep_fn(min(remaining, 0.05))
