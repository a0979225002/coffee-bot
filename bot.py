from telegram import BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)
from config import BOT_TOKEN, VERIFY_KEY, SET_NAME, CHOOSE_DRINK, CHOOSE_TEMP, CHOOSE_BEAN, CHOOSE_TIME, CONFIRM_OVERWRITE, logger
from storage import load_users
from scheduler import scheduler, update_user_schedule
from handlers import (
    start, verify_key, set_name,
    order_start, choose_drink, choose_temp, choose_bean,
    auto_start, auto_confirm, auto_choose_drink, auto_choose_temp, auto_choose_bean, auto_choose_time, cancel_auto,
    skip_cmd, skip_toggle,
    help_cmd, apikey_cmd, status, who, list_all,
)


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # --- 對話流程 ---

    start_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            VERIFY_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, verify_key)],
            SET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_name)],
        },
        fallbacks=[],
        allow_reentry=True,
        conversation_timeout=120,
    )

    order_handler = ConversationHandler(
        entry_points=[CommandHandler("order", order_start)],
        states={
            CHOOSE_DRINK: [CallbackQueryHandler(choose_drink, pattern=r"^drink:")],
            CHOOSE_TEMP: [CallbackQueryHandler(choose_temp, pattern=r"^temp:")],
            CHOOSE_BEAN: [CallbackQueryHandler(choose_bean, pattern=r"^bean:")],
        },
        fallbacks=[],
        allow_reentry=True,
        conversation_timeout=120,
    )

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
        allow_reentry=True,
        conversation_timeout=120,
    )

    # --- 註冊 handlers ---

    app.add_handler(start_handler)
    app.add_handler(order_handler)
    app.add_handler(auto_handler)
    app.add_handler(CommandHandler("skip", skip_cmd))
    app.add_handler(CallbackQueryHandler(skip_toggle, pattern=r"^skip:"))
    app.add_handler(CommandHandler("cancel_auto", cancel_auto))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("who", who))
    app.add_handler(CommandHandler("list", list_all))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("apikey", apikey_cmd))

    async def error_handler(update, context):
        logger.error(f"發生錯誤: {context.error}")

    app.add_error_handler(error_handler)

    # --- 排程 ---

    app.bot_data["scheduler"] = scheduler

    users = load_users()
    for uid, user in users.items():
        if user.get("auto"):
            update_user_schedule(uid, user, app.bot)

    scheduler.start()

    # --- Telegram 指令選單 ---

    async def post_init(application):
        await application.bot.set_my_commands([
            BotCommand("order", "手動訂咖啡"),
            BotCommand("auto", "設定每日自動訂購"),
            BotCommand("skip", "選擇要跳過的日期"),
            BotCommand("status", "查看你的設定"),
            BotCommand("who", "查看誰設了自動訂購"),
            BotCommand("list", "查看所有使用者"),
            BotCommand("cancel_auto", "取消自動訂購"),
            BotCommand("apikey", "查看API Key"),
            BotCommand("help", "顯示所有指令"),
        ])

    app.post_init = post_init

    logger.info("Bot 啟動中...")
    app.run_polling()


if __name__ == "__main__":
    main()
