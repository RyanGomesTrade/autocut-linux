
import json
import os

WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(WORKSPACE_DIR, "web_config.json")
DEFAULT_CONFIG = {
    "youtube_profile_index": 0,
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
            merged = DEFAULT_CONFIG.copy()
            merged.update(saved)
            return merged
    return DEFAULT_CONFIG.copy()

print(f"Config: {load_config()}")
print(f"youtube_profiles.json exists: {os.path.exists('youtube_profiles.json')}")
if os.path.exists('youtube_profiles.json'):
    with open('youtube_profiles.json', 'r') as f:
        print(f"Profiles: {json.load(f)}")
