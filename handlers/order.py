from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler
from config import DRINKS, TEMPS, BEANS, CHOOSE_DRINK, CHOOSE_TEMP, CHOOSE_BEAN
from storage import load_users
from form import submit_form


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
