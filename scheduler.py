from datetime import date
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import logger
from storage import load_users, save_users
from form import submit_form

# 全域 scheduler
scheduler = AsyncIOScheduler(timezone="Asia/Taipei")


def get_skip_dates(uid: str) -> set:
    """從 users.json 讀取某使用者的跳過日期"""
    users = load_users()
    user = users.get(uid, {})
    return set(user.get("skip_dates", []))


def save_skip_dates(uid: str, dates: set):
    """將跳過日期存入 users.json"""
    users = load_users()
    if uid in users:
        # 只保留今天及之後的日期
        today = date.today().isoformat()
        users[uid]["skip_dates"] = sorted([d for d in dates if d >= today])
        save_users(users)


async def auto_order_for_user(uid: str, bot):
    """幫單一使用者自動訂咖啡"""
    today = date.today().isoformat()
    skip = get_skip_dates(uid)

    if today in skip:
        skip.discard(today)
        save_skip_dates(uid, skip)
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
