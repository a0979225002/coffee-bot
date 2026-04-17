import json
import os
import re
import uuid
import logging
from datetime import date
from pathlib import Path

import requests
import browser_cookie3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- 設定 ---
CONFIG_FILE = Path(__file__).parent / "config.json"
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

# Google Form 表單網址
FORM_BASE = "https://docs.google.com/forms/d/e/1FAIpQLSd0zY40JLXJsJjKh5Ri2BlE3SdrD0XqVWy0lTWnz_JrSOwO2w"
FORM_VIEW_URL = f"{FORM_BASE}/viewform"
FORM_SUBMIT_URL = f"{FORM_BASE}/formResponse"


def get_chrome_session():
    """建立帶有 Chrome cookie 的 requests Session"""
    cj = browser_cookie3.chrome(domain_name='.google.com')
    s = requests.Session()
    for c in cj:
        s.cookies.set_cookie(c)
    s.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    })
    return s

# 飲品選單
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

# 時間選項（8:30~10:30，每 30 分鐘）
TIMES = ["08:30", "09:00", "09:30", "10:00", "10:30"]

# 對話狀態
VERIFY_KEY, SET_NAME, CHOOSE_DRINK, CHOOSE_TEMP, CHOOSE_BEAN, CHOOSE_TIME, CONFIRM_OVERWRITE = range(7)

# 使用者資料存檔
DATA_FILE = Path(__file__).parent / "users.json"

# 今日跳過名單（記憶體內，每天重置）
skip_today: set[str] = set()
skip_date: str = ""


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_users() -> dict:
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return {}


def save_users(users: dict):
    DATA_FILE.write_text(json.dumps(users, ensure_ascii=False, indent=2))


def submit_form(name: str, drink: str, temp: str, bean: str, note: str = "") -> tuple[bool, str]:
    """提交 Google Form，回傳 (成功與否, 訊息)"""
    try:
        s = get_chrome_session()
    except Exception as e:
        logger.error(f"無法讀取 Chrome cookie: {e}")
        return False, "無法讀取 Chrome cookie，請確認 Chrome 已登入 Google"

    try:
        r = s.get(FORM_VIEW_URL, timeout=10)
    except Exception as e:
        logger.error(f"無法載入表單頁面: {e}")
        return False, "無法連線到 Google Form"

    if "登入" in r.text and "英文名" not in r.text:
        return False, "Google 登入已過期，請重新在 Chrome 登入 Google 帳號"

    # 從頁面抓取隱藏欄位
    fbzx_match = re.findall(r'name="fbzx" value="([^"]+)"', r.text)
    if not fbzx_match:
        return False, "無法解析表單（找不到 fbzx）"
    fbzx = fbzx_match[0]

    # 從 data-params 解析欄位結構
    # 格式：%.@.[問題ID,"標題",null,類型,[[子欄位ID,...]]]
    # 類型 0 = 文字輸入，類型 2 = 單選（radio）
    field_blocks = re.findall(r'data-params="(%.@\.[^"]+)"', r.text)
    text_fields = []   # (子欄位ID) 文字輸入
    radio_fields = []  # (子欄位ID) 單選
    for block in field_blocks:
        block = block.replace('&quot;', '"').replace('&amp;', '&')
        # 取得欄位類型：null,0 = 文字, null,2 = 單選
        type_match = re.search(r',null,(\d+),\[\[(\d+)', block)
        if type_match:
            field_type = int(type_match.group(1))
            sub_id = type_match.group(2)
            if field_type == 0:
                text_fields.append(sub_id)
            elif field_type == 2:
                radio_fields.append(sub_id)

    if len(radio_fields) < 3 or len(text_fields) < 1:
        return False, f"表單欄位數量不符（文字:{len(text_fields)}, 單選:{len(radio_fields)}）"

    # 組合提交資料
    # 文字欄位：[0]=英文名, [1]=備註（若有）
    # 單選欄位：[0]=飲品, [1]=冰熱, [2]=咖啡豆
    data = {
        f'entry.{text_fields[0]}': name,
        f'entry.{radio_fields[0]}': drink,
        f'entry.{radio_fields[0]}_sentinel': '',
        f'entry.{radio_fields[1]}': temp,
        f'entry.{radio_fields[1]}_sentinel': '',
        f'entry.{radio_fields[2]}': bean,
        f'entry.{radio_fields[2]}_sentinel': '',
        'fvv': '1',
        'pageHistory': '0',
        'fbzx': fbzx,
    }
    if len(text_fields) > 1:
        data[f'entry.{text_fields[1]}'] = note

    try:
        r2 = s.post(FORM_SUBMIT_URL, data=data, headers={'Referer': FORM_VIEW_URL}, timeout=10)
    except Exception as e:
        logger.error(f"提交請求失敗: {e}")
        return False, "網路錯誤，無法提交表單"

    if r2.status_code == 400:
        logger.warning(f"[提交失敗] {name} | {drink}/{temp}/{bean} | HTTP 400")
        return False, "表單拒絕提交（400），可能欄位格式有誤"
    if r2.status_code != 200:
        logger.warning(f"[提交失敗] {name} | {drink}/{temp}/{bean} | HTTP {r2.status_code}")
        return False, f"表單回傳錯誤（HTTP {r2.status_code}）"

    if "回覆" in r2.text or "recorded" in r2.text.lower():
        logger.info(f"[提交成功] {name} | {drink}/{temp}/{bean}")
        return True, "提交成功"

    logger.warning(f"[提交未確認] {name} | {drink}/{temp}/{bean} | 回應中無確認關鍵字")
    return False, "提交後未收到確認，請到表單頁面確認是否成功"


HELP_TEXT = (
    "所有指令：\n"
    "/order - 手動訂咖啡\n"
    "/auto - 設定每日自動訂購（含時間）\n"
    "/skip - 今天跳過自動訂購，明天恢復\n"
    "/status - 查看你的設定\n"
    "/who - 查看誰設了自動訂購\n"
    "/list - 查看所有使用者\n"
    "/cancel_auto - 取消自動訂購\n"
    "/cancel - 取消當前操作（流程卡住時使用）\n"
    "/apikey - 查看API Key\n"
    "/help - 顯示此說明"
)


# --- Bot 指令 ---

async def apikey_cmd(update: Update, context):
    users = load_users()
    uid = str(update.effective_user.id)
    if uid not in users:
        await update.message.reply_text("請先用 /start 註冊。")
        return
    my_key = users[uid].get("api_key", "未記錄")
    await update.message.reply_text(f"你的 API Key：\n`{my_key}`", parse_mode="Markdown")


async def help_cmd(update: Update, context):
    users = load_users()
    uid = str(update.effective_user.id)
    if uid not in users:
        await update.message.reply_text("請先用 /start 註冊。")
        return
    await update.message.reply_text(HELP_TEXT)


async def start(update: Update, context):
    users = load_users()
    uid = str(update.effective_user.id)
    if uid in users:
        await update.message.reply_text(f"嗨 {users[uid]['name']}！輸入 /help 查看所有指令。")
        return ConversationHandler.END

    await update.message.reply_text(
        "歡迎使用歐客佬咖啡訂購 Bot！\n\n"
        "請輸入 API Key："
    )
    return VERIFY_KEY


async def verify_key(update: Update, context):
    if update.message.text.strip() != ACCESS_KEY:
        await update.message.reply_text("API Key 錯誤，請重新輸入：")
        return VERIFY_KEY

    # 暫存這組 Key 給 set_name 用
    context.user_data["registered_key"] = ACCESS_KEY

    # 驗證成功後立刻換新 Key，舊的就失效了
    new_key = regenerate_api_key()
    logger.info(f"API Key 已更新：{new_key}")

    await update.message.reply_text(
        "驗證成功！\n\n"
        "這個 Bot 可以幫你：\n"
        "1. 每天自動訂咖啡，不用再手動填表單\n"
        "2. 也可以臨時手動訂購或換口味\n\n"
        "請輸入你的英文名（用來填寫表單）："
    )
    return SET_NAME



async def set_name(update: Update, context):
    users = load_users()
    uid = str(update.effective_user.id)
    name = update.message.text.strip()
    users[uid] = {"name": name, "auto": None, "api_key": context.user_data.get("registered_key", "")}
    save_users(users)
    await update.message.reply_text(
        f"設定完成！{name}\n\n"
        f"以下是所有指令：\n"
        f"/order - 手動訂咖啡（選飲品 → 冰熱 → 豆子）\n"
        f"/auto - 設定每日自動訂購（含時間）\n"
        f"/skip - 今天跳過自動訂購，明天恢復\n"
        f"/status - 查看你的設定\n"
        f"/who - 查看誰設了自動訂購\n"
        f"/list - 查看所有使用者\n"
        f"/cancel_auto - 取消自動訂購\n\n"
        f"建議先用 /auto 設定每日自動訂購，之後就不用管了！"
    )
    return ConversationHandler.END


# --- 手動訂購流程 ---

async def order_start(update: Update, context):
    users = load_users()
    uid = str(update.effective_user.id)
    if uid not in users:
        await update.message.reply_text("請先用 /start 設定你的英文名。")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton(d, callback_data=f"drink:{d}")]
        for d in DRINKS
    ]
    await update.message.reply_text("今天要喝什麼？", reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSE_DRINK


async def choose_drink(update: Update, context):
    query = update.callback_query
    await query.answer()
    drink = query.data.replace("drink:", "")
    context.user_data["drink"] = drink

    if drink == "Pass":
        uid = str(query.from_user.id)
        users = load_users()
        name = users[uid]["name"]
        ok, msg = submit_form(name, "Pass", "冰的", "")
        if ok:
            await query.edit_message_text("好的，今天 Pass ☕")
        else:
            await query.edit_message_text(f"提交失敗：{msg}")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton(t, callback_data=f"temp:{t}")]
        for t in TEMPS
    ]
    await query.edit_message_text("冰的還是熱的？", reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSE_TEMP


async def choose_temp(update: Update, context):
    query = update.callback_query
    await query.answer()
    temp = query.data.replace("temp:", "")
    context.user_data["temp"] = temp

    keyboard = [
        [InlineKeyboardButton(b, callback_data=f"bean:{b}")]
        for b in BEANS
    ]
    await query.edit_message_text("咖啡豆喜好？", reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSE_BEAN


async def choose_bean(update: Update, context):
    query = update.callback_query
    await query.answer()
    bean = query.data.replace("bean:", "")

    uid = str(query.from_user.id)
    users = load_users()
    name = users[uid]["name"]
    drink = context.user_data["drink"]
    temp = context.user_data["temp"]

    ok, msg = submit_form(name, drink, temp, bean)
    if ok:
        await query.edit_message_text(f"已訂購！\n☕ {drink}\n🧊 {temp}\n🫘 {bean}")
    else:
        await query.edit_message_text(f"提交失敗：{msg}")
    return ConversationHandler.END


# --- 自動訂購設定 ---

async def auto_start(update: Update, context):
    users = load_users()
    uid = str(update.effective_user.id)
    if uid not in users:
        await update.message.reply_text("請先用 /start 設定你的英文名。")
        return ConversationHandler.END

    if users[uid].get("auto"):
        a = users[uid]["auto"]
        keyboard = [
            [InlineKeyboardButton("重新設定", callback_data="auto_confirm:yes"),
             InlineKeyboardButton("取消", callback_data="auto_confirm:no")],
        ]
        name = users[uid]["name"]
        await update.message.reply_text(
            f"{name}，你目前已設定自動訂購：\n"
            f"☕ {a['drink']} / {a['temp']} / {a['bean']} / {a.get('time', '09:00')}\n\n"
            f"要重新設定嗎?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return CONFIRM_OVERWRITE

    keyboard = [
        [InlineKeyboardButton(d, callback_data=f"auto_drink:{d}")]
        for d in DRINKS if d != "Pass"
    ]
    await update.message.reply_text("設定每日自動訂購的飲品：", reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSE_DRINK


async def auto_confirm(update: Update, context):
    query = update.callback_query
    await query.answer()
    choice = query.data.replace("auto_confirm:", "")

    if choice == "no":
        await query.edit_message_text("好的，維持原本的設定。")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton(d, callback_data=f"auto_drink:{d}")]
        for d in DRINKS if d != "Pass"
    ]
    await query.edit_message_text("設定每日自動訂購的飲品：", reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSE_DRINK


async def auto_choose_drink(update: Update, context):
    query = update.callback_query
    await query.answer()
    drink = query.data.replace("auto_drink:", "")
    context.user_data["auto_drink"] = drink

    keyboard = [
        [InlineKeyboardButton(t, callback_data=f"auto_temp:{t}")]
        for t in TEMPS
    ]
    await query.edit_message_text("冰的還是熱的？", reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSE_TEMP


async def auto_choose_temp(update: Update, context):
    query = update.callback_query
    await query.answer()
    temp = query.data.replace("auto_temp:", "")
    context.user_data["auto_temp"] = temp

    keyboard = [
        [InlineKeyboardButton(b, callback_data=f"auto_bean:{b}")]
        for b in BEANS
    ]
    await query.edit_message_text("咖啡豆喜好？", reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSE_BEAN


async def auto_choose_bean(update: Update, context):
    query = update.callback_query
    await query.answer()
    bean = query.data.replace("auto_bean:", "")
    context.user_data["auto_bean"] = bean

    keyboard = [
        [InlineKeyboardButton(t, callback_data=f"auto_time:{t}")]
        for t in TIMES
    ]
    await query.edit_message_text("幾點幫你訂？", reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSE_TIME


async def auto_choose_time(update: Update, context):
    query = update.callback_query
    await query.answer()
    time_str = query.data.replace("auto_time:", "")

    uid = str(query.from_user.id)
    users = load_users()
    users[uid]["auto"] = {
        "drink": context.user_data["auto_drink"],
        "temp": context.user_data["auto_temp"],
        "bean": context.user_data["auto_bean"],
        "time": time_str,
    }
    save_users(users)

    drink = context.user_data["auto_drink"]
    temp = context.user_data["auto_temp"]
    bean = context.user_data["auto_bean"]
    await query.edit_message_text(
        f"自動訂購已設定！\n"
        f"每週一到五 {time_str} 自動幫你訂：\n"
        f"☕ {drink}\n🧊 {temp}\n🫘 {bean}\n\n"
        f"取消請用 /cancel_auto"
    )

    # 更新排程
    update_user_schedule(uid, users[uid], query.bot)

    return ConversationHandler.END


async def skip_today_cmd(update: Update, context):
    global skip_today, skip_date
    today = date.today().isoformat()
    if skip_date != today:
        skip_today = set()
        skip_date = today
    uid = str(update.effective_user.id)
    skip_today.add(uid)
    await update.message.reply_text("好的，今天不幫你自動訂購。明天恢復正常。")


async def cancel_auto(update: Update, context):
    users = load_users()
    uid = str(update.effective_user.id)
    if uid in users:
        users[uid]["auto"] = None
        save_users(users)
    # 移除該使用者的排程
    scheduler = context.bot_data.get("scheduler")
    if scheduler:
        job_id = f"auto_{uid}"
        job = scheduler.get_job(job_id)
        if job:
            job.remove()
    await update.message.reply_text("已取消自動訂購。")


async def who(update: Update, context):
    users = load_users()
    auto_users = [
        f"- {u['name']}：☕ {u['auto']['drink']} / {u['auto']['temp']} / {u['auto']['bean']} / {u['auto'].get('time', '09:00')}"
        for u in users.values()
        if u.get("auto")
    ]
    if auto_users:
        text = "自動訂購名單：\n" + "\n".join(auto_users)
    else:
        text = "目前沒有人設定自動訂購。"
    await update.message.reply_text(text)


async def list_all(update: Update, context):
    users = load_users()
    all_users = [
        f"- {u['name']}" + (f"（auto {u['auto'].get('time', '09:00')}）" if u.get("auto") else "")
        for u in users.values()
    ]
    if all_users:
        text = "所有使用者：\n" + "\n".join(all_users)
    else:
        text = "目前沒有人註冊。"
    await update.message.reply_text(text)


async def status(update: Update, context):
    users = load_users()
    uid = str(update.effective_user.id)
    if uid not in users:
        await update.message.reply_text("請先用 /start 設定。")
        return

    user = users[uid]
    text = f"👤 {user['name']}\n"
    if user.get("auto"):
        a = user["auto"]
        text += f"自動訂購：☕ {a['drink']} / {a['temp']} / {a['bean']} / {a.get('time', '09:00')}"
    else:
        text += "自動訂購：未設定"
    await update.message.reply_text(text)


# --- 每日自動訂購排程 ---

async def auto_order_for_user(uid: str, bot):
    """幫單一使用者自動訂咖啡"""
    global skip_today, skip_date
    today = date.today().isoformat()
    if skip_date != today:
        skip_today = set()
        skip_date = today

    if uid in skip_today:
        try:
            await bot.send_message(chat_id=int(uid), text="今天已跳過自動訂購。")
        except Exception:
            pass
        return

    users = load_users()
    user = users.get(uid)
    if not user or not user.get("auto"):
        return

    a = user["auto"]
    ok, err = submit_form(user["name"], a["drink"], a["temp"], a["bean"])
    if ok:
        msg = f"已自動訂購！\n☕ {a['drink']} / {a['temp']} / {a['bean']}"
    else:
        msg = f"自動訂購失敗：{err}\n請手動用 /order 訂購。"
    try:
        await bot.send_message(chat_id=int(uid), text=msg)
    except Exception as e:
        logger.error(f"發送通知給 {uid} 失敗: {e}")


def update_user_schedule(uid: str, user: dict, bot):
    """新增或更新某使用者的排程"""
    job_id = f"auto_{uid}"
    job = scheduler.get_job(job_id)
    if job:
        job.remove()

    if not user.get("auto"):
        return

    time_str = user["auto"].get("time", "09:00")
    hour, minute = map(int, time_str.split(":"))
    scheduler.add_job(
        auto_order_for_user,
        "cron",
        day_of_week="mon-fri",
        hour=hour,
        minute=minute,
        args=[uid, bot],
        id=job_id,
        replace_existing=True,
    )
    logger.info(f"排程已設定：{uid} 每週一到五 {time_str}")


# 全域 scheduler
scheduler = AsyncIOScheduler(timezone="Asia/Taipei")


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # 取消對話指令
    async def cancel(update: Update, context):
        await update.message.reply_text("已取消。")
        return ConversationHandler.END

    cancel_handler = CommandHandler("cancel", cancel)

    # 註冊流程：/start
    start_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            VERIFY_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, verify_key)],
            SET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_name)],
        },
        fallbacks=[cancel_handler],
        conversation_timeout=300,
    )

    # 手動訂購流程：/order
    order_handler = ConversationHandler(
        entry_points=[CommandHandler("order", order_start)],
        states={
            CHOOSE_DRINK: [CallbackQueryHandler(choose_drink, pattern=r"^drink:")],
            CHOOSE_TEMP: [CallbackQueryHandler(choose_temp, pattern=r"^temp:")],
            CHOOSE_BEAN: [CallbackQueryHandler(choose_bean, pattern=r"^bean:")],
        },
        fallbacks=[cancel_handler],
        conversation_timeout=300,
    )

    # 自動訂購設定流程：/auto
    auto_handler = ConversationHandler(
        entry_points=[CommandHandler("auto", auto_start)],
        states={
            CONFIRM_OVERWRITE: [CallbackQueryHandler(auto_confirm, pattern=r"^auto_confirm:")],
            CHOOSE_DRINK: [CallbackQueryHandler(auto_choose_drink, pattern=r"^auto_drink:")],
            CHOOSE_TEMP: [CallbackQueryHandler(auto_choose_temp, pattern=r"^auto_temp:")],
            CHOOSE_BEAN: [CallbackQueryHandler(auto_choose_bean, pattern=r"^auto_bean:")],
            CHOOSE_TIME: [CallbackQueryHandler(auto_choose_time, pattern=r"^auto_time:")],
        },
        fallbacks=[cancel_handler],
        conversation_timeout=300,
    )

    app.add_handler(start_handler)
    app.add_handler(order_handler)
    app.add_handler(auto_handler)
    app.add_handler(CommandHandler("skip", skip_today_cmd))
    app.add_handler(CommandHandler("cancel_auto", cancel_auto))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("who", who))
    app.add_handler(CommandHandler("list", list_all))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("apikey", apikey_cmd))

    async def error_handler(update, context):
        logger.error(f"發生錯誤: {context.error}")

    app.add_error_handler(error_handler)

    # 把 scheduler 存到 bot_data 給 cancel_auto 用
    app.bot_data["scheduler"] = scheduler

    # 啟動時載入所有已設定的使用者排程
    users = load_users()
    for uid, user in users.items():
        if user.get("auto"):
            update_user_schedule(uid, user, app.bot)

    scheduler.start()

    # 設定 Telegram 指令選單
    async def post_init(application):
        from telegram import BotCommand
        await application.bot.set_my_commands([
            BotCommand("order", "手動訂咖啡"),
            BotCommand("auto", "設定每日自動訂購"),
            BotCommand("skip", "今天跳過自動訂購"),
            BotCommand("status", "查看你的設定"),
            BotCommand("who", "查看誰設了自動訂購"),
            BotCommand("list", "查看所有使用者"),
            BotCommand("cancel_auto", "取消自動訂購"),
            BotCommand("cancel", "取消當前操作"),
            BotCommand("apikey", "查看API Key"),
            BotCommand("help", "顯示所有指令"),
        ])

    app.post_init = post_init

    logger.info("Bot 啟動中...")
    app.run_polling()


if __name__ == "__main__":
    main()
