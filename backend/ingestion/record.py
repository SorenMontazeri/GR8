import os
import time
from datetime import datetime, timezone
import cv2

CAMERA_IP = "192.168.0.90"
USERNAME = "student"
PASSWORD = "student"
RTSP_URL = f"rtsp://{USERNAME}:{PASSWORD}@{CAMERA_IP}/axis-media/media.amp"

DEFAULT_RECORDING_DURATION = 5
OUTPUT_FOLDER = os.path.join(os.path.dirname(__file__), "..", "recordings")


def get_recording_path():
    os.makedirs(OUTPUT_FOLDER, exist_ok=True) # If sibling fodler "record" doesnt exist create it
    time = datetime.now(timezone.utc)
    name = f"D{time.strftime("%Y-%m-%d")}-T{time.strftime("%H-%M-%S")}.mp4"

    return os.path.join(OUTPUT_FOLDER, name)
    

def setup_rtsp_capture(url):
    return cv2.VideoCapture(url)


# Could be optimized by using "ffmpeg -c copy" to skip decoding and re-encoding but thats for later
def record(capture, duration_seconds):
    output_path = get_recording_path()
    
    # Video properties 
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = capture.get(cv2.CAP_PROP_FPS)

    # Create writer
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    # Write
    start = time.time()
    while True:
        if time.time() - start >= duration_seconds:
            break

        ok, frame = capture.read()
        if not ok or frame is None:
            break

        writer.write(frame)

    writer.release()
    return True


def main(): # Testing
    capture = setup_rtsp_capture(RTSP_URL)
    record(capture, DEFAULT_RECORDING_DURATION)
    capture.release()
    

if __name__ == "__main__":
    main()
