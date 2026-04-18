from datetime import date, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from config import WEEKDAY_NAMES
from scheduler import skip_dates


def get_next_workdays(count=5):
    """取得未來 count 個工作日（週一到週五）"""
    days = []
    d = date.today()
    while len(days) < count:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def _build_skip_buttons(user_skips):
    """產生跳過日期的按鈕列表"""
    workdays = get_next_workdays(5)
    buttons = []
    for d in workdays:
        label = f"週{WEEKDAY_NAMES[d.weekday()]} {d.month}/{d.day}"
        if d.isoformat() in user_skips:
            label += " (已跳過)"
        buttons.append([InlineKeyboardButton(label, callback_data=f"skip:{d.isoformat()}")])
    buttons.append([InlineKeyboardButton("完成", callback_data="skip:done")])
    return buttons


def _skip_summary(user_skips):
    """產生已跳過日期的文字摘要"""
    skipped = sorted([s for s in user_skips if s >= date.today().isoformat()])
    if not skipped:
        return None
    return ", ".join(
        f"週{WEEKDAY_NAMES[date.fromisoformat(s).weekday()]} {date.fromisoformat(s).month}/{date.fromisoformat(s).day}"
        for s in skipped
    )


async def skip_cmd(update: Update, context):
    uid = str(update.effective_user.id)
    user_skips = skip_dates.get(uid, set())
    buttons = _build_skip_buttons(user_skips)

    summary = _skip_summary(user_skips)
    if summary:
        text = f"目前已跳過：{summary}\n\n點選日期可切換跳過/取消跳過："
    else:
        text = "點選要跳過自動訂購的日期："

    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def skip_toggle(update: Update, context):
    query = update.callback_query
    await query.answer()
    uid = str(query.from_user.id)
    target_date = query.data.split(":", 1)[1]

    # 按「完成」
    if target_date == "done":
        user_skips = skip_dates.get(uid, set())
        summary = _skip_summary(user_skips)
        if summary:
            text = f"設定完成！已跳過：{summary}"
        else:
            text = "目前沒有跳過任何日期。"
        await query.edit_message_text(text)
        return

    # 切換跳過/恢復
    if uid not in skip_dates:
        skip_dates[uid] = set()

    d = date.fromisoformat(target_date)
    day_label = f"週{WEEKDAY_NAMES[d.weekday()]} {d.month}/{d.day}"

    if target_date in skip_dates[uid]:
        skip_dates[uid].remove(target_date)
        action = f"已恢復 {day_label} 的自動訂購"
    else:
        skip_dates[uid].add(target_date)
        action = f"已跳過 {day_label} 的自動訂購"

    buttons = _build_skip_buttons(skip_dates[uid])
    summary = _skip_summary(skip_dates[uid])
    if summary:
        text = f"{action}\n\n目前已跳過：{summary}\n\n點選日期可切換跳過/取消跳過："
    else:
        text = f"{action}\n\n點選要跳過自動訂購的日期："

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
