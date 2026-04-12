import json
import os
import logging
from datetime import date
from pathlib import Path

import requests
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

# Google Form 表單網址與欄位 ID（依你的表單調整）
FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSd0zY40JLXJsJjKh5Ri2BlE3SdrD0XqVWy0lTWnz_JrSOwO2w/formResponse"
ENTRY_NAME = "entry.453017699"       # 英文名
ENTRY_DRINK = "entry.929171591"      # 飲品選擇
ENTRY_TEMP = "entry.324546308"       # 冰的/熱的
ENTRY_BEAN = "entry.1689470523"      # 咖啡豆喜好
ENTRY_NOTE = "entry.1443756478"      # 備註

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
SET_NAME, CHOOSE_DRINK, CHOOSE_TEMP, CHOOSE_BEAN, CHOOSE_TIME, CONFIRM_OVERWRITE = range(6)

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


def submit_form(name: str, drink: str, temp: str, bean: str, note: str = "") -> bool:
    """提交 Google Form"""
    data = {
        ENTRY_NAME: name,
        ENTRY_DRINK: drink,
        ENTRY_TEMP: temp,
        ENTRY_BEAN: bean,
        ENTRY_NOTE: note,
    }
    try:
        r = requests.post(FORM_URL, data=data, timeout=10)
        return r.status_code == 200
    except Exception as e:
        logger.error(f"提交表單失敗: {e}")
        return False


HELP_TEXT = (
    "所有指令：\n"
    "/order - 手動訂咖啡\n"
    "/auto - 設定每日自動訂購（含時間）\n"
    "/skip - 今天跳過自動訂購，明天恢復\n"
    "/status - 查看你的設定\n"
    "/who - 查看誰設了自動訂購\n"
    "/list - 查看所有使用者\n"
    "/cancel_auto - 取消自動訂購\n"
    "/help - 顯示此說明"
)


# --- Bot 指令 ---

async def help_cmd(update: Update, context):
    await update.message.reply_text(HELP_TEXT)


async def start(update: Update, context):
    users = load_users()
    uid = str(update.effective_user.id)
    if uid in users:
        name = users[uid]['name']
        keyboard = [
            [InlineKeyboardButton(f"維持 {name}", callback_data="keep_name:yes"),
             InlineKeyboardButton("改名", callback_data="keep_name:no")],
        ]
        await update.message.reply_text(
            f"嗨 {name}！名字正確嗎?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return SET_NAME

    await update.message.reply_text(
        "歡迎使用歐客佬咖啡訂購 Bot！\n\n"
        "這個 Bot 可以幫你：\n"
        "1. 每天自動訂咖啡，不用再手動填表單\n"
        "2. 也可以臨時手動訂購或換口味\n\n"
        "首先，請輸入你的英文名（用來填寫表單）："
    )
    return SET_NAME


async def keep_name_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    choice = query.data.replace("keep_name:", "")

    if choice == "yes":
        await query.edit_message_text(HELP_TEXT)
        return ConversationHandler.END

    await query.edit_message_text("請輸入新的英文名：")
    return SET_NAME


async def set_name(update: Update, context):
    users = load_users()
    uid = str(update.effective_user.id)
    name = update.message.text.strip()
    users[uid] = {"name": name, "auto": None}
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
        ok = submit_form(name, "Pass", "冰的", "")
        if ok:
            await query.edit_message_text("好的，今天 Pass ☕")
        else:
            await query.edit_message_text("提交失敗，請稍後再試。")
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

    ok = submit_form(name, drink, temp, bean)
    if ok:
        await query.edit_message_text(f"已訂購！\n☕ {drink}\n🧊 {temp}\n🫘 {bean}")
    else:
        await query.edit_message_text("提交失敗，請稍後再試。")
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
    ok = submit_form(user["name"], a["drink"], a["temp"], a["bean"])
    msg = (
        f"已自動訂購！\n☕ {a['drink']} / {a['temp']} / {a['bean']}"
        if ok
        else "自動訂購失敗，請手動用 /order 訂購。"
    )
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

    # 註冊流程：/start
    start_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={SET_NAME: [
            CallbackQueryHandler(keep_name_callback, pattern=r"^keep_name:"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, set_name),
        ]},
        fallbacks=[],
    )

    # 手動訂購流程：/order
    order_handler = ConversationHandler(
        entry_points=[CommandHandler("order", order_start)],
        states={
            CHOOSE_DRINK: [CallbackQueryHandler(choose_drink, pattern=r"^drink:")],
            CHOOSE_TEMP: [CallbackQueryHandler(choose_temp, pattern=r"^temp:")],
            CHOOSE_BEAN: [CallbackQueryHandler(choose_bean, pattern=r"^bean:")],
        },
        fallbacks=[],
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
        fallbacks=[],
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

    # 把 scheduler 存到 bot_data 給 cancel_auto 用
    app.bot_data["scheduler"] = scheduler

    # 啟動時載入所有已設定的使用者排程
    users = load_users()
    for uid, user in users.items():
        if user.get("auto"):
            update_user_schedule(uid, user, app.bot)

    scheduler.start()

    logger.info("Bot 啟動中...")
    app.run_polling()


if __name__ == "__main__":
    main()
