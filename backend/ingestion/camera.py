from record_ffmpeg import *
import paho.mqtt.client as mqtt
import time
import json


class Camera:
    def __init__(self, camera_id: str, rtsp_url: str, ffmpeg: str, broker_host: str, broker_port: int, segment_seconds: int = 10):
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.recording_process = None
        self.mqtt_client = mqtt.Client()

        self.init_recording(ffmpeg, segment_seconds)
        self.init_buffer()
        self.init_mqtt(broker_host, broker_port)

    def init_recording(self, ffmpeg, segment_seconds):
        self.recording_process = start_recording_ffmpeg(ffmpeg, self.rtsp_url, self.camera_id, segment_seconds)

    def init_mqtt(self, broker_host, broker_port):
        self.mqtt_client.connect(broker_host, broker_port, 60)
        self.mqtt_client.on_message = self.on_message
        self.mqtt_client.subscribe(f"camera/{self.camera_id}")
        self.mqtt_client.loop_start()

    def on_message(self, client, userdata, msg): # Will probably turn into the analys logic (gets called on the mqtt listener thread whenver a new message is sent)
        payload = msg.payload.decode("utf-8", errors="replace")
        data = json.loads(payload)

        #with open("test.json", "w", encoding="utf-8") as f:
        #    json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(data)


    def init_buffer(self):
        pass

    def stop_recording(self):
        stop_recording(self.recording_process)
        self.recording_process = None


def main():
    camera_ip = "192.168.0.90"
    username = "student"
    password = "student"
    rtsp_url = f"rtsp://{username}:{password}@{camera_ip}/axis-media/media.amp"
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    broker_host = "10.255.255.1"
    broker_port = 1883

    camera = Camera("1", rtsp_url, ffmpeg, broker_host, broker_port, 5)
    time.sleep(7)
    camera.stop_recording()


if __name__ == "__main__":
    main()
