from __future__ import annotations

import json
import threading

import paho.mqtt.client as mqtt


class CameraMqttPrinter:
    def __init__(
        self,
        camera_id: str,
        broker_host: str,
        broker_port: int,
    ) -> None:
        self.camera_id = camera_id
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.mqtt_client = mqtt.Client()

        self.init_mqtt()

    def init_mqtt(self) -> None:
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_message = self.on_message

        self.mqtt_client.connect(self.broker_host, self.broker_port, 60)
        self.mqtt_client.loop_start()

    def on_connect(self, client, userdata, flags, rc) -> None:
        if rc == 0:
            topic = f"camera/{self.camera_id}"
            print(f"[mqtt] connected to broker")
            print(f"[mqtt] subscribing to topic: {topic}")
            client.subscribe(topic)
        else:
            print(f"[mqtt] failed to connect, return code: {rc}")

    def on_message(self, client, userdata, msg) -> None:
        payload = msg.payload.decode("utf-8", errors="replace")

        print("\n--- MQTT MESSAGE ---")
        print(f"topic: {msg.topic}")
        print(f"payload: {payload}")

        try:
            data = json.loads(payload)
            print("json:")
            print(json.dumps(data, indent=2))
        except json.JSONDecodeError:
            print("[mqtt] payload is not valid JSON")

    def stop(self) -> None:
        self.mqtt_client.loop_stop()
        self.mqtt_client.disconnect()
        print("[mqtt] disconnected")


def main() -> None:
    camera_id = "1"

    broker_host = "10.255.255.1"
    broker_port = 1883

    mqtt_printer = CameraMqttPrinter(
        camera_id=camera_id,
        broker_host=broker_host,
        broker_port=broker_port,
    )

    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        mqtt_printer.stop()


if __name__ == "__main__":
    main()