import json
import uuid
import logging
from pathlib import Path

# --- 路徑 ---
BASE_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "config.json"
DATA_FILE = BASE_DIR / "users.json"

# --- 載入設定 ---
if not CONFIG_FILE.exists():
    print("請先複製 config.example.json 為 config.json，並填入你的 Bot Token")
    exit(1)

_config = json.loads(CONFIG_FILE.read_text())
BOT_TOKEN = _config["BOT_TOKEN"]
ACCESS_KEY = _config["ACCESS_KEY"]


def regenerate_api_key() -> str:
    """產生新的 API Key 並存入 config.json"""
    global ACCESS_KEY
    new_key = str(uuid.uuid4())
    ACCESS_KEY = new_key
    _config["ACCESS_KEY"] = new_key
    CONFIG_FILE.write_text(json.dumps(_config, ensure_ascii=False, indent=2))
    return new_key


# --- Google Form ---
FORM_BASE = "https://docs.google.com/forms/d/e/1FAIpQLSd0zY40JLXJsJjKh5Ri2BlE3SdrD0XqVWy0lTWnz_JrSOwO2w"
FORM_VIEW_URL = f"{FORM_BASE}/viewform"
FORM_SUBMIT_URL = f"{FORM_BASE}/formResponse"

# --- 飲品選單 ---
DRINKS = [
    "美式",
    "拿鐵 (+30)",
    "卡布奇諾 (+30)",
    "風味拿鐵 - 焦糖 (+40)",
    "風味拿鐵 - 榛果 (+40)",
    "風味拿鐵 - 香草(+40)",
    "Pass",
]
TEMPS = ["冰的", "熱的"]
BEANS = ["酸", "不酸"]
TIMES = ["08:30", "09:00", "09:30", "10:00", "10:30"]

# --- 對話狀態 ---
VERIFY_KEY, SET_NAME, CHOOSE_DRINK, CHOOSE_TEMP, CHOOSE_BEAN, CHOOSE_TIME, CONFIRM_OVERWRITE = range(7)

# --- 星期名稱 ---
WEEKDAY_NAMES = ["一", "二", "三", "四", "五", "六", "日"]

# --- Logger ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("coffee-bot")
