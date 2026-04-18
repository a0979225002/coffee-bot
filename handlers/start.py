from telegram import Update
from telegram.ext import ConversationHandler
from config import ACCESS_KEY, VERIFY_KEY, SET_NAME, logger, regenerate_api_key
from storage import load_users, save_users


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
    from config import ACCESS_KEY
    if update.message.text.strip() != ACCESS_KEY:
        await update.message.reply_text("API Key 錯誤，請重新輸入：")
        return VERIFY_KEY

    context.user_data["registered_key"] = ACCESS_KEY
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
        f"/skip - 選擇要跳過自動訂購的日期\n"
        f"/status - 查看你的設定\n"
        f"/who - 查看誰設了自動訂購\n"
        f"/list - 查看所有使用者\n"
        f"/cancel_auto - 取消自動訂購\n\n"
        f"建議先用 /auto 設定每日自動訂購，之後就不用管了！"
    )
    return ConversationHandler.END
