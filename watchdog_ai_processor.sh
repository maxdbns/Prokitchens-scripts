#!/usr/bin/env bash
cd /zpool/one/maxime.debaugnies

PID_FILE="ai_request_processor.pid"
LOCK_FILE="ai_request_processor.lock"
LOG="logs/ai_request_processor.log"
WATCHDOG_LOG="logs/watchdog_ai_processor.log"

while true; do
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE" 2>/dev/null || true)
        if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
            : # alive
        else
            echo "$(date '+%Y-%m-%d %H:%M:%S') ai_processor mort (PID $PID), relance..." >> "$WATCHDOG_LOG"
            rm -f "$PID_FILE" "$LOCK_FILE"
            nohup python3 ai_request_processor.py >> "$LOG" 2>&1 &
            echo $! > "$PID_FILE"
            echo "$(date '+%Y-%m-%d %H:%M:%S') ai_processor relance (PID $(cat $PID_FILE))" >> "$WATCHDOG_LOG"
        fi
    else
        echo "$(date '+%Y-%m-%d %H:%M:%S') pas de PID file, lancement ai_processor..." >> "$WATCHDOG_LOG"
        rm -f "$LOCK_FILE"
        nohup python3 ai_request_processor.py >> "$LOG" 2>&1 &
        echo $! > "$PID_FILE"
    fi
    sleep 60
done
