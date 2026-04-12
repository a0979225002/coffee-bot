#!/bin/bash
cd "$(dirname "$0")"

if pgrep -f "bot.py" > /dev/null; then
    echo "Bot 已經在運行中"
    read -p "是否關閉？(Y/n) " choice
    case "$choice" in
        [Nn])
            echo "維持運行"
            ;;
        *)
            pkill -f "bot.py"
            echo "Bot 已關閉"
            ;;
    esac
else
    source venv/bin/activate
    nohup python bot.py > bot.log 2>&1 &
    echo "Bot 已啟動"
fi
