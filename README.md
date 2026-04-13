# Coffee Order Bot

Telegram Bot 自動訂購咖啡，搭配 Google Form 表單提交。

這是一個教學專案，示範如何用 Python 建立 Telegram Bot，整合 Google Form 自動填寫與排程功能。

## 功能

| 指令 | 說明 |
|------|------|
| `/start` | 新使用者註冊（需輸入 API Key） |
| `/order` | 手動訂咖啡（選飲品 → 冰熱 → 豆子） |
| `/auto` | 設定每日自動訂購（含時間，08:30~10:30） |
| `/skip` | 今天跳過自動訂購，明天恢復 |
| `/status` | 查看個人設定 |
| `/who` | 查看誰設了自動訂購 |
| `/list` | 查看所有使用者 |
| `/apikey` | 查看自己的 API Key |
| `/cancel_auto` | 取消自動訂購 |
| `/help` | 顯示所有指令 |

## 安全機制

- 新使用者加入需輸入 **API Key** 驗證
- 每次有新使用者註冊成功後，API Key 會自動更換，舊的立即失效
- 每位使用者的 API Key 會個別保存，可透過 `/apikey` 查看自己的
- 管理者可透過 `start.sh` 查看當前最新的 API Key，提供給下一位加入的人

## 架構

```
coffee-bot/
├── bot.py              # 主程式
├── config.json         # Bot Token + API Key（不上傳）
├── config.example.json # config 範本
├── users.json          # 使用者資料（自動產生，不上傳）
├── start.sh            # 啟動/管理腳本
├── login.py            # Google 登入工具（表單需登入時使用）
├── requirements.txt    # Python 套件
└── .gitignore
```

## 使用技術

- **python-telegram-bot** — Telegram Bot API 的 Python 封裝
- **APScheduler** — 排程器，用來定時自動訂購
- **requests** — HTTP 請求，用來提交 Google Form
- **browser-cookie3** — 讀取 Chrome 瀏覽器的 Google 登入 cookie
- **Google Form** — 透過 POST 請求直接提交表單，自動解析 entry ID

## 快速開始

### 1. 建立 Telegram Bot

1. 下載 [Telegram](https://telegram.org/)（手機或電腦都可以）
2. 在 Telegram 搜尋 `@BotFather`，點進去對話
3. 輸入 `/newbot`
4. BotFather 會問你 Bot 的**顯示名稱**，輸入你想要的名字（例如 `咖啡通知`）
5. 再輸入 Bot 的 **username**，必須以 `_bot` 結尾（例如 `my_coffee_bot`）
6. 建立成功後，BotFather 會給你一組 **Bot Token**，格式像 `123456789:ABCdefGHI...`，複製起來

### 2. 測試 Bot 能不能發訊息（選讀）

Bot 程式寫好前，可以先手動測試 Bot 能不能發訊息給你：

1. 在 Telegram 搜尋你剛建的 Bot，點進去按 **START**，傳一句 `hi`
2. 在瀏覽器打開（把 `你的TOKEN` 換成你的 Bot Token）：
   ```
   https://api.telegram.org/bot你的TOKEN/getUpdates
   ```
3. 在回傳的 JSON 中找到 `"chat":{"id": 123456789}`，這就是你的 **Chat ID**
4. 用以下指令測試發送訊息：
   ```bash
   curl -s -X POST "https://api.telegram.org/bot你的TOKEN/sendMessage" \
     -H "Content-Type: application/json" \
     -d '{"chat_id": 你的CHAT_ID, "text": "測試成功！"}'
   ```
5. Telegram 收到訊息就代表 Bot 設定正確

> 注意：Bot 程式啟動 polling 後，`getUpdates` 會被程式佔用而拿不到結果。這步只適用於程式啟動前的測試。Bot 啟動後，使用者的 Chat ID 會在 `/start` 時由程式自動取得。

### 3. 設定專案

```bash
git clone <你的 repo 網址>
cd coffee-bot

# 建立虛擬環境
python3 -m venv venv
source venv/bin/activate

# 安裝套件
pip install -r requirements.txt

# 建立設定檔
cp config.example.json config.json
```

編輯 `config.json`：

```json
{
  "BOT_TOKEN": "你從 BotFather 拿到的 Token",
  "ACCESS_KEY": "自訂 API Key（建議用 UUID，例如 python3 -c \"import uuid; print(uuid.uuid4())\"）"
}
```

### 4. 啟動

```bash
bash start.sh
```

`start.sh` 功能：
- Bot 沒在跑 → 自動啟動
- Bot 已在跑 → 顯示選單：關閉 Bot / 查看 API Key / 離開

> macOS 使用者：雙擊如果打開文字編輯器，右鍵 → 打開檔案的應用程式 → 選**終端機**。

### 5. 開始使用

到 Telegram 找你的 Bot，按 START，輸入 API Key 後設定英文名即可。

## 學習重點

這個專案涵蓋了以下概念：

1. **Telegram Bot API** — 如何建立互動式 Bot，使用 InlineKeyboard 做選單
2. **ConversationHandler** — 多步驟對話流程（選飲品 → 選冰熱 → 選豆子 → 選時間）
3. **Google Form 自動提交** — 動態解析表單 HTML 取得 entry ID，支援表單欄位變更
4. **APScheduler 排程** — 定時執行任務，支援每個使用者不同時間
5. **JSON 檔案儲存** — 簡單的使用者資料持久化
6. **API Key 驗證** — 一次性 Key 機制，註冊後自動換新
7. **browser-cookie3** — 讀取瀏覽器 cookie 解決需要登入的表單

## 如何找到 Google Form 的 entry ID

1. 打開你的 Google Form 網址
2. 右鍵 → 檢視原始碼
3. 搜尋 `entry.`，每個欄位都有一組 `entry.數字` 的 ID
4. 把找到的 ID 替換到 `bot.py` 中對應的變數

> 本專案已支援自動解析 entry ID，表單欄位變更時不需手動更新。

## 注意事項

- Bot 需要一直運行才會執行排程（電腦不能關機或休眠）
- 如果表單需要 Google 登入，需在運行 Bot 的電腦上用 Chrome 登入 Google 帳號
- `config.json` 和 `users.json` 不會上傳到 Git
- 如果表單網址更換，需要手動更新 `bot.py` 中的 `FORM_BASE`
