#!/usr/bin/env bash
set -e
cd /zpool/one/maxime.debaugnies

PID_FILE="ai_request_processor.pid"
WATCHDOG_PID="watchdog_ai_processor.pid"

if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null || true)
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo "AI Processor deja actif (PID $OLD_PID)."
        echo "Arret: bash stop_ai_processor.sh"
        exit 1
    fi
fi

mkdir -p logs

echo "Demarrage du AI Request Processor..."
nohup python3 ai_request_processor.py >> logs/ai_request_processor.log 2>&1 &
echo $! > "$PID_FILE"
echo "Processor lance (PID $(cat $PID_FILE))"

echo "Demarrage du watchdog..."
nohup bash watchdog_ai_processor.sh >> logs/watchdog_ai_processor.log 2>&1 &
echo $! > "$WATCHDOG_PID"
echo "Watchdog lance (PID $(cat $WATCHDOG_PID))"

echo "Log: tail -f logs/ai_request_processor.log"
