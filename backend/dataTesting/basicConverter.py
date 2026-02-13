def transform_event(src: dict, *, default_source: str = "live", embed_snapshot: bool = False) -> dict:
    """
    Transformerar kamerahändelse till målformat.
    - Rensar bort boxar/paths.
    - Lägger bild som referens (image://{image.id}), eller bäddar in base64 om embed_snapshot=True.
    """
    # Hämta basfält
    event_id = src.get("id")  # kan ersättas med ett nytt UUID om så önskas
    camera_id = str(src.get("channel_id")) if src.get("channel_id") is not None else None

    # track_id
    track_id = None
    parts = src.get("parts") or []
    if parts and isinstance(parts, list):
        track_id = (parts[0] or {}).get("object_track_id")

    # timestamp (använder image.timestamp i första hand)
    timestamp = None
    image = src.get("image") or {}
    if "timestamp" in image and image["timestamp"]:
        timestamp = image["timestamp"]
    else:
        # fallback: end_time eller start_time
        timestamp = src.get("end_time") or src.get("start_time")

    # snapshot_ref vs inbäddning
    snapshot_ref = None
    snapshot_base64 = None
    image_id = image.get("id")
    if embed_snapshot:
        snapshot_base64 = image.get("data")  # inte rekommenderat för stora flöden
    else:
        if image_id:
            snapshot_ref = f"image://{image_id}"

    # Plocka ut nyttolast (payload), rensa bort boxar och paths
    # 1) Hantera klasser – om ni vill spara hela listan, kommentera "top_class" och använd classes direkt.
    classes = src.get("classes") or []
    top_class = None
    if classes:
        c0 = classes[0]
        top_class = {
            "type": c0.get("type"),
            "score": c0.get("score"),
            "upper_clothing_colors": c0.get("upper_clothing_colors") or [],
            "lower_clothing_colors": c0.get("lower_clothing_colors") or []
        }

    payload = {
        "duration": src.get("duration"),
        "start_time": src.get("start_time"),
        "end_time": src.get("end_time"),
        "image_id": image_id,
    }

    # Lägg till klassinformation
    if top_class:
        payload.update(top_class)
    # Alternativ: spara alla klasser
    # payload["classes"] = classes

    # OBS: Lägger inte till image.data, crop_box eller path.
    # Om ni måste bädda in base64 (inte rekommenderat), lägg det här:
    if embed_snapshot and snapshot_base64:
        payload["snapshot_base64"] = snapshot_base64

    # Bygg slutresultat
    result = {
        "event_id": event_id,
        "track_id": track_id,
        "camera_id": camera_id,
        "timestamp": timestamp,
        "snapshot_ref": snapshot_ref,
        "source": default_source,
        "payload": payload
    }
    return result
