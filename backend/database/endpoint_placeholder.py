from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import base64
from pathlib import Path

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/image/{name}")
def get_image(name: str):
    if name == "bov":
        image_path = Path(__file__).with_name(f"output.jpg")
        image_bytes = image_path.read_bytes()
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        return {
            "name": name,
            "image": image_b64,
        }
    else:
        raise HTTPException(status_code=404, detail="Image not found")
