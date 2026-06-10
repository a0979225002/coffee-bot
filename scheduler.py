import asyncio
from datetime import date
from apscheduler.events import EVENT_JOB_MISSED, EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
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
    # submit_form 是同步阻塞呼叫（requests + browser_cookie3），必須丟進 thread，
    # 否則會卡住整個 event loop（polling、心跳、所有 handler 都在同一個 loop 上）
    ok, err = await asyncio.to_thread(
        submit_form, user["name"], a["drink"], a["temp"], a["bean"]
    )
    if ok:
        msg = f"已自動訂購！\n☕ {a['drink']} / {a['temp']} / {a['bean']}"
    else:
        msg = f"自動訂購失敗：{err}\n請手動用 /order 訂購。"
    try:
        await bot.send_message(chat_id=int(uid), text=msg)
    except Exception as e:
        logger.error(f"發送通知給 {uid} 失敗: {e}")


def update_user_schedule(uid: str, user: dict, bot):
    """新增、更新或移除某使用者的排程（auto 為空時移除），是排程異動的唯一入口"""
    job_id = f"auto_{uid}"

    if not user.get("auto"):
        job = scheduler.get_job(job_id)
        if job:
            job.remove()
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
        # macOS 睡眠會凍結 asyncio 計時器，醒來後 job 可能晚數十分鐘才觸發：
        # 一小時內遲到照樣下單（咖啡晚訂好過沒訂），超過才視為 missed 交給通知器
        coalesce=True,
        misfire_grace_time=3600,
    )
    logger.info(f"排程已設定：{uid} 每週一到五 {time_str}")


async def _heartbeat():
    pass


def setup_heartbeat():
    """每 60 秒喚醒 scheduler 一次，強制用牆鐘重新計算主計時器。

    asyncio 計時器走的 monotonic 時鐘在 macOS 睡眠期間會停走，bot 一天只有
    一個 10:30 的喚醒點時，整夜累積的凍結量會原封不動變成隔天的觸發延遲。
    心跳讓主計時器每分鐘重掛一次，誤差最多累積一分鐘左右。不要移除。
    """
    scheduler.add_job(
        _heartbeat,
        "interval",
        seconds=60,
        id="heartbeat",
        coalesce=True,
        misfire_grace_time=None,  # 不設容忍上限，心跳永遠不會被判 missed
    )


def setup_job_error_listener():
    """job 內未捕捉的例外不會自動浮上主程式，掛監聽器把完整 traceback 寫進 log"""
    def on_job_event(event):
        if getattr(event, "exception", None):
            logger.error(
                f"任務 [{event.job_id}] 執行出錯: {event.exception}\n{event.traceback or ''}"
            )

    scheduler.add_listener(on_job_event, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)


def setup_misfire_notifier(bot):
    """註冊 misfire 監聽器：cron 因延遲超過容忍時間被放棄時通知使用者。

    通知具備重試機制（共 4 次：立即、30 秒、2 分、5 分後），所有結果都會
    寫進 bot.log，事後 grep `misfire` 即可追溯每次 missed 事件與通知狀態。
    """
    async def notify_with_retry(uid: str, text: str, job_id: str):
        delays = [0, 30, 120, 300]
        for attempt, delay in enumerate(delays, start=1):
            if delay:
                await asyncio.sleep(delay)
            try:
                await bot.send_message(chat_id=int(uid), text=text)
                logger.info(f"misfire 通知送出成功 (job={job_id}, 第 {attempt} 次嘗試)")
                return
            except Exception as e:
                logger.warning(f"misfire 通知第 {attempt} 次嘗試失敗 (job={job_id}): {e}")
        logger.error(f"misfire 通知最終放棄 (job={job_id})：{len(delays)} 次重試皆失敗")

    def on_missed(event):
        job_id = event.job_id
        if not job_id.startswith("auto_"):
            return
        uid = job_id[len("auto_"):]
        scheduled = getattr(event, "scheduled_run_time", None)
        sched_str = scheduled.strftime("%Y-%m-%d %H:%M") if scheduled else "未知時間"
        logger.warning(f"misfire：{job_id} 預定 {sched_str} 未執行（超過容忍時間被放棄）")
        text = (
            f"今日自動訂購未執行：預定 {sched_str} 觸發時系統延遲過久"
            "（例如網路斷線、Mac 睡眠），請手動用 /order 下單。"
        )
        try:
            asyncio.create_task(notify_with_retry(uid, text, job_id))
        except RuntimeError as e:
            logger.error(f"misfire 通知無法排程 task (job={job_id}): {e}")

    scheduler.add_listener(on_missed, EVENT_JOB_MISSED)
