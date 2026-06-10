#!/bin/bash
cd "$(dirname "$0")"

# 用 .bot.pid 精準記住自己的 PID，避免跟其他同名 bot.py（如 StockRobot）互相誤判/誤殺
PIDFILE=".bot.pid"

# 如果 config.json 不存在，自動建立並生成 API Key
if [ ! -f config.json ]; then
    python3 -c "import json,uuid; json.dump({'BOT_TOKEN':'你的TOKEN','ACCESS_KEY':str(uuid.uuid4())},open('config.json','w'),indent=2)"
    echo "已自動建立 config.json（含 API Key）"
    echo "請先編輯 config.json 填入你的 Bot Token，再重新執行"
    exit 0
fi

# 用 PID file 精準判斷自己是否在跑（不靠 pgrep bot.py，避免抓到其他專案的 bot.py）
RUNNING_PID=""
if [ -f "$PIDFILE" ]; then
    CANDIDATE=$(cat "$PIDFILE" 2>/dev/null)
    if [ -n "$CANDIDATE" ] && kill -0 "$CANDIDATE" 2>/dev/null; then
        RUNNING_PID="$CANDIDATE"
    else
        rm -f "$PIDFILE"  # 殘留的 PID file，清掉
    fi
fi

if [ -n "$RUNNING_PID" ]; then
    while true; do
        echo ""
        echo "Bot 已經在運行中（PID=$RUNNING_PID）"
        echo ""
        echo "1) 關閉 Bot"
        echo "2) 查看 API Key"
        echo "3) 離開"
        read -p "請選擇 (1/2/3): " choice
        case "$choice" in
            1)
                kill "$RUNNING_PID" 2>/dev/null
                sleep 1
                if kill -0 "$RUNNING_PID" 2>/dev/null; then
                    echo "尚未結束，強制關閉"
                    kill -9 "$RUNNING_PID" 2>/dev/null
                    sleep 1
                fi
                rm -f "$PIDFILE"
                echo "Bot 已關閉"
                break
                ;;
            2)
                key=$(python3 -c "import json; print(json.load(open('config.json'))['ACCESS_KEY'])")
                echo ""
                echo "目前的 API Key："
                echo "$key"
                ;;
            3)
                break
                ;;
            *)
                echo "請輸入 1、2 或 3"
                ;;
        esac
    done
else
    source venv/bin/activate
    # 附加模式：重啟不清掉舊 log，失效當時的證據才留得住
    nohup python bot.py >> bot.log 2>&1 &
    NEW_PID=$!
    echo "$NEW_PID" > "$PIDFILE"
    echo "Bot 已啟動（PID=$NEW_PID）"
fi
