from telegram import Update
from storage import load_users

HELP_TEXT = (
    "所有指令：\n"
    "/order - 手動訂咖啡\n"
    "/auto - 設定每日自動訂購（含時間）\n"
    "/skip - 選擇要跳過自動訂購的日期\n"
    "/status - 查看你的設定\n"
    "/who - 查看誰設了自動訂購\n"
    "/list - 查看所有使用者\n"
    "/cancel_auto - 取消自動訂購\n"
    "/apikey - 查看API Key\n"
    "/help - 顯示此說明"
)


async def help_cmd(update: Update, context):
    users = load_users()
    uid = str(update.effective_user.id)
    if uid not in users:
        await update.message.reply_text("請先用 /start 註冊。")
        return
    await update.message.reply_text(HELP_TEXT)


async def apikey_cmd(update: Update, context):
    users = load_users()
    uid = str(update.effective_user.id)
    if uid not in users:
        await update.message.reply_text("請先用 /start 註冊。")
        return
    my_key = users[uid].get("api_key", "未記錄")
    await update.message.reply_text(f"你的 API Key：\n`{my_key}`", parse_mode="Markdown")


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
