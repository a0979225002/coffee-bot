#!/bin/bash
cd "$(dirname "$0")"

# 如果 config.json 不存在，自動建立並生成 API Key
if [ ! -f config.json ]; then
    python3 -c "import json,uuid; json.dump({'BOT_TOKEN':'你的TOKEN','ACCESS_KEY':str(uuid.uuid4())},open('config.json','w'),indent=2)"
    echo "已自動建立 config.json（含 API Key）"
    echo "請先編輯 config.json 填入你的 Bot Token，再重新執行"
    exit 0
fi

if pgrep -f "bot.py" > /dev/null; then
    while true; do
        echo ""
        echo "Bot 已經在運行中"
        echo ""
        echo "1) 關閉 Bot"
        echo "2) 查看 API Key"
        echo "3) 離開"
        read -p "請選擇 (1/2/3): " choice
        case "$choice" in
            1)
                pkill -f "bot.py"
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
    nohup python bot.py > bot.log 2>&1 &
    echo "Bot 已啟動"
fi
