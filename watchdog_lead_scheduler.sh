#!/usr/bin/env bash
# Watchdog pour lead_scheduler.py — relance le scheduler s'il meurt.
set -e

ROOT="/zpool/one/maxime.debaugnies"
cd "$ROOT"

PID_FILE="lead_scheduler.pid"
LOCK_FILE="lead_scheduler.lock"
LOG_FILE="lead_scheduler.log"
WATCHDOG_LOG="watchdog_lead_scheduler.log"

while true; do
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE" 2>/dev/null || true)
        if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
            echo "$(date '+%Y-%m-%d %H:%M:%S') scheduler alive (PID $PID)" >> "$WATCHDOG_LOG"
        else
            echo "$(date '+%Y-%m-%d %H:%M:%S') scheduler dead (PID $PID), restarting..." >> "$WATCHDOG_LOG"
            rm -f "$PID_FILE" "$LOCK_FILE"
            nohup python3 lead_scheduler.py >> "$LOG_FILE" 2>&1 &
            echo $! > "$PID_FILE"
            echo "$(date '+%Y-%m-%d %H:%M:%S') scheduler restarted (PID $(cat $PID_FILE))" >> "$WATCHDOG_LOG"
        fi
    else
        echo "$(date '+%Y-%m-%d %H:%M:%S') no PID file, starting scheduler..." >> "$WATCHDOG_LOG"
        rm -f "$LOCK_FILE"
        nohup python3 lead_scheduler.py >> "$LOG_FILE" 2>&1 &
        echo $! > "$PID_FILE"
    fi
    sleep 60
done
