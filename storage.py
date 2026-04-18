import json
from config import DATA_FILE


def load_users() -> dict:
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return {}


def save_users(users: dict):
    DATA_FILE.write_text(json.dumps(users, ensure_ascii=False, indent=2))
