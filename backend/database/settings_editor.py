import json
from pathlib import Path
SETTINGS_PATH = Path(__file__).with_name("settings.json")

def default_settings():
    return {
        "min_event_duration": 0,
        "prompt_fullframe_snapshot": "",
        "prompt_uniform_movement": "",
        "fullframe_time": -1,
        "uniform_samplerate": 1,
        "uniform_samplerate_value": 0,
        "movement_tracker_type": 1,
        "movement_tracker_type_threshhold": 1,
        "movement_samplerate": 1,
        "movement_samplerate_value": 0,
    }

def save_settings(settings):
    f = open(SETTINGS_PATH, "w", encoding="utf-8")
    json.dump(settings, f, ensure_ascii=False, indent=2)
    f.close()

def load_settings():
    settings = default_settings()
    if not SETTINGS_PATH.exists():
        save_settings(settings)
        return settings
    f = open(SETTINGS_PATH, "r", encoding="utf-8")
    saved = json.load(f)
    f.close()
    settings.update(saved)
    return settings

def normalized_settings_json(settings: dict) -> str:
    return json.dumps(settings, sort_keys=True, separators=(",", ":"))