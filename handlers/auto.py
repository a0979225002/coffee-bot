from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler
from config import DRINKS, TEMPS, BEANS, TIMES, CHOOSE_DRINK, CHOOSE_TEMP, CHOOSE_BEAN, CHOOSE_TIME, CONFIRM_OVERWRITE
from storage import load_users, save_users
from scheduler import update_user_schedule


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

    update_user_schedule(uid, users[uid], query.bot)
    return ConversationHandler.END


async def cancel_auto(update: Update, context):
    users = load_users()
    uid = str(update.effective_user.id)
    if uid in users:
        users[uid]["auto"] = None
        save_users(users)
    scheduler = context.bot_data.get("scheduler")
    if scheduler:
        job_id = f"auto_{uid}"
        job = scheduler.get_job(job_id)
        if job:
            job.remove()
    await update.message.reply_text("已取消自動訂購。")
