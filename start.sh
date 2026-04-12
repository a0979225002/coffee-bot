#!/bin/bash
cd "$(dirname "$0")"

# 如果已經在跑就不重複啟動
if pgrep -f "python bot.py" > /dev/null; then
    echo "Bot 已經在運行中"
    exit 0
fi

source venv/bin/activate
nohup python bot.py > bot.log 2>&1 &
echo "Bot 已啟動"
