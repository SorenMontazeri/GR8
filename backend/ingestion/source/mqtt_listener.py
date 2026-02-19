# ingestion_/source/mqtt_listener.py
from __future__ import annotations

from typing import Callable, Optional

# Den här filen är en STUB så länge ni inte kopplat MQTT-broker.
# Idén: mqtt_listener tar emot JSON-meddelanden och callbackar vidare dem som dict.

class MqttListener:
    def __init__(self) -> None:
        self._running = False

    def start(self, on_message: Callable[[dict], None]) -> None:
        """Starta lyssning (stub). I verkligheten kopplas MQTT client här."""
        self._running = True
        # TODO: implementera med paho-mqtt eller axis-rekommenderad client

    def stop(self) -> None:
        self._running = False