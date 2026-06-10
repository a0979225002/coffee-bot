# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 專案定位

教學用 Telegram Bot：整合 Google Form 自動提交 + APScheduler 每日排程訂購咖啡。所有訊息、註解、commit message 都使用繁體中文。

## 常用指令

```bash
# 啟動 / 管理 Bot（互動式：未跑時自動背景啟動，已跑時顯示選單可關閉/查 API Key）
bash start.sh

# 開發時直接前景執行（在已啟動的 venv 中）
source venv/bin/activate
python bot.py

# 停止背景 Bot（用 start.sh 選單，或直接讀 .bot.pid；勿用 pkill -f bot.py，會誤殺同名的其他專案 bot.py）
kill "$(cat .bot.pid)"

# 查看即時 log
tail -f bot.log
```

沒有 lint / 測試框架，請不要假設它們存在。

## 設定檔

- `config.json` — `BOT_TOKEN` + `ACCESS_KEY`（一次性註冊金鑰）。不進版控；首次執行 `start.sh` 會自動生成。
- `users.json` — 使用者資料（`name`、`auto` 排程、`api_key`、`skip_dates`）。執行時自動寫入，不進版控。

## 架構重點

入口 `bot.py` 只做組裝：建立 `Application` → 註冊三條 `ConversationHandler`（`/start`、`/order`、`/auto`）+ 單步 handlers → 從 `users.json` 重建排程 → `run_polling()`。對話狀態整數常數集中在 `config.py`，handlers 透過 import 使用，修改流程時必須同步兩邊。

**三層資料流**：
1. `handlers/*` — Telegram 互動層，每個指令一個模組，handler 名稱從 `handlers/__init__.py` re-export 後由 `bot.py` 統一掛載。
2. `storage.py` — `users.json` 讀寫。極簡，每次操作都整檔 `load_users()` → 修改 → `save_users()`，沒有 in-memory cache。
3. `form.py` / `scheduler.py` — 外部整合層。

**Google Form 提交（`form.py`）的關鍵設計**：不寫死 `entry.xxx` ID。每次提交都重新 GET 表單 HTML，用正則從 `data-params` 解析欄位類型（`0` = 文字、`2` = 單選）與 ID，因此表單欄位調整（新增/重排）不需改 code。Session cookie 透過 `browser_cookie3.chrome()` 直接讀取本機 Chrome 的 `.google.com` cookie，所以執行 Bot 的機器必須是有登入 Google 的 macOS + Chrome。若 cookie 過期，整條排程會安靜失敗，要在 Chrome 重新登入。`FORM_BASE` 寫死在 `config.py`，表單換網址時要手動更新。

> 注意 `login.py` 用 Selenium 產生 `cookies.json` 的流程**目前沒有被 `form.py` 讀取**（runtime 只吃 `browser_cookie3.chrome()`），是歷史備援腳本。修改 cookie 流程時不要假設 `cookies.json` 參與 runtime。

**排程（`scheduler.py`）**：全域 `AsyncIOScheduler`（Asia/Taipei），每位使用者一個 `cron` job（週一到週五、`job_id = f"auto_{uid}"`）。`update_user_schedule()` 以 `replace_existing=True` 取代既有 job、`auto` 為空時移除 job，是新增/改時間/取消的唯一入口（`/cancel_auto` 也走它）。Bot 重啟後 `bot.py` 會掃 `users.json` 重建所有 auto 使用者的 job。

**macOS 睡眠 vs 排程計時器（重要，勿回退）**：asyncio 計時器走的 monotonic 時鐘在 macOS 睡眠期間會停走——電腦睡多久、計時器就慢多久，曾造成「跑一週後 10:30 全部失效、重啟才正常」的 bug。對策有三，缺一不可：(1) `heartbeat` job 每 60 秒強制 scheduler 用牆鐘重掛主計時器；(2) auto job 設 `misfire_grace_time=3600` + `coalesce=True`，一小時內遲到照樣下單；(3) misfire 監聽器在超過一小時被放棄時通知使用者手動下單。另外 `submit_form` 是同步阻塞呼叫，所有呼叫點（`scheduler.py`、`handlers/order.py`）都必須用 `asyncio.to_thread()` 包住，否則會卡死整個 event loop。

**`skip_dates` 流程**：跳過日期存在 `users[uid]["skip_dates"]`（ISO 字串陣列）。`auto_order_for_user` 發現今天在清單中時，會立即從清單移除再通知使用者，不需手動清理。`save_skip_dates()` 會順便濾掉過期日期。

**API Key 輪替**：`/start` → `verify_key` 驗證成功的當下，`regenerate_api_key()` 會立即把 `config.json` 的 `ACCESS_KEY` 換成新的 UUID，舊 key 失效。下一位使用者要註冊時，管理者透過 `start.sh` 的選單查看當前 key 再轉交。注意 `handlers/start.py:verify_key` 是用 `from config import ACCESS_KEY` **函式內局部 import** 才能讀到最新值——不要把它改成檔案頂層 import，否則重生後拿到的是舊值。

## 對話流程注意事項

三條 `ConversationHandler` 都設定 `allow_reentry=True` + `conversation_timeout=120`，沒有 fallback。這是刻意的：使用者卡住時重新執行同一個指令即可重置，不需要 `/cancel`。新增需要多步互動的指令時沿用此模式。

handler 內要拿 bot 實例一律用 `context.bot`——PTB 21 的 `CallbackQuery` 沒有 `.bot` 屬性，寫 `query.bot` 會在執行當下丟 `AttributeError`（訊息已送出、動作卻沒做，很難察覺）。

`CallbackQueryHandler` 的 `pattern` 前綴在各指令間是分開的（`/order` 用 `drink:` / `temp:` / `bean:`、`/auto` 用 `auto_drink:` / `auto_temp:` / `auto_bean:` / `auto_time:` / `auto_confirm:`、`/skip` 用 `skip:`），避免 callback 路由衝突，擴充時請保留此命名規則。
