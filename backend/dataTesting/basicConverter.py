import json
import uuid
from typing import Any, Dict


def transform_event(src: Dict[str, Any]) -> Dict[str, Any]:
    """
    Minimal transform function based on your required fields.
    Adjust as needed.
    """
    event_id = src.get("id") or str(uuid.uuid4())
    camera_id = str(src.get("channel_id"))
    image = src.get("image", {})
    classes = src.get("classes", [])
    parts = src.get("parts", [])

    # track_id
    track_id = None
    if parts and "object_track_id" in parts[0]:
        track_id = parts[0]["object_track_id"]

    # timestamp → image.timestamp first
    timestamp = (
        image.get("timestamp")
        or src.get("end_time")
        or src.get("start_time")
    )

    # snapshot_ref (not embedding base64)
    snapshot_ref = None
    if "id" in image:
        snapshot_ref = f"image://{image['id']}"

    # payload (clean)
    payload = {
        "duration": src.get("duration"),
        "start_time": src.get("start_time"),
        "end_time": src.get("end_time"),
        "image_id": image.get("id"),
    }

    # put top class only (optional)
    if classes:
        c = classes[0]
        payload.update({
            "type": c.get("type"),
            "score": c.get("score"),
            "upper_clothing_colors": c.get("upper_clothing_colors", []),
            "lower_clothing_colors": c.get("lower_clothing_colors", []),
        })

    return {
        "event_id": event_id,
        "track_id": track_id,
        "camera_id": camera_id,
        "timestamp": timestamp,
        "snapshot_ref": snapshot_ref,
        "source": "live",
        "payload": payload,
    }


def main():
    print("Enter input JSON filename:")
    input_file = input("> ").strip()

    print("Enter output JSON filename:")
    output_file = input("> ").strip()

    # Load input JSON
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Transform (single object OR list)
    if isinstance(data, list):
        transformed = [transform_event(ev) for ev in data]
    else:
        transformed = transform_event(data)

    # Save output JSON
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(transformed, f, indent=2, ensure_ascii=False)

    print(f"\nDone! Wrote transformed JSON to: {output_file}")


if __name__ == "__main__":
    main()