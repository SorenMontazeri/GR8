import os, cv2, base64
from datetime import datetime, timedelta

DIR = os.path.join(os.path.dirname(__file__), "recordings/1")

def extract(t, clip=10):
    for f in os.listdir(DIR):
        try:
            s = datetime.strptime(f, "D%Y-%m-%d-T%H-%M-%S.mp4")
            if s <= t < s + timedelta(seconds=clip):
                p = os.path.join(DIR, f)
                cap = cv2.VideoCapture(p)
                cap.set(cv2.CAP_PROP_POS_FRAMES,
                        int((t - s).total_seconds() * cap.get(cv2.CAP_PROP_FPS)))
                ok, frame = cap.read(); cap.release()
                if not ok:
                    raise RuntimeError("Kunde inte läsa frame")

                # Encode to JPEG in memory
                _, buffer = cv2.imencode(".jpg", frame)
                return base64.b64encode(buffer).decode("utf-8")

        except:
            pass

    raise FileNotFoundError("Ingen matchande video")


if __name__ == "__main__":
    b64 = extract(datetime(2026, 2, 23, 12, 24, 57, 300000))
    with open("frame.b64.txt", "w", encoding="ascii") as f:
        f.write(b64)
    print("Wrote frame.b64.txt, length:", len(b64))