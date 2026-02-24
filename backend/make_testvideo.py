import os, cv2, numpy as np
from datetime import datetime

DIR = os.path.join(os.path.dirname(__file__), "recordings")
os.makedirs(DIR, exist_ok=True)

def make_test_clip(seconds=10, fps=30, size=(1280, 720)):
    start_dt = datetime.now().replace(microsecond=0)
    base = start_dt.strftime("D%Y-%m-%d-T%H-%M-%S")

    # Försök MP4 först
    candidates = [
        (f"{base}.mp4", "mp4v"),
        (f"{base}.avi", "MJPG"),  # fallback som brukar funka nästan alltid
    ]

    w, h = size
    for filename, fourcc_str in candidates:
        path = os.path.join(DIR, filename)
        fourcc = cv2.VideoWriter_fourcc(*fourcc_str)
        out = cv2.VideoWriter(path, fourcc, fps, size)

        print("Trying:", path, "codec:", fourcc_str, "opened:", out.isOpened())
        if not out.isOpened():
            out.release()
            continue

        for i in range(seconds * fps):
            t = i / fps
            n = int(round(100 - (t / seconds) * 100))
            frame = np.zeros((h, w, 3), np.uint8)
            cv2.putText(frame, f"{n}", (w//3, h//2),
                        cv2.FONT_HERSHEY_SIMPLEX, 8, (255,255,255), 16, cv2.LINE_AA)
            cv2.putText(frame, f"t={t:.3f}s", (50, h-60),
                        cv2.FONT_HERSHEY_SIMPLEX, 2, (255,255,255), 4, cv2.LINE_AA)
            out.write(frame)

        out.release()
        print("Created:", path)
        return path

    raise RuntimeError("Kunde inte skapa video: varken mp4v eller MJPG fungerade på din maskin.")

if __name__ == "__main__":
    make_test_clip()
