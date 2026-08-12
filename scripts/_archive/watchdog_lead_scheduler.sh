#!/usr/bin/env bash
# Watchdog pour lead_scheduler.py — relance le scheduler s'il meurt.
# Lancé via setsid par start_lead_scheduler.sh pour survivre aux fermetures de terminal.

ROOT="/zpool/one/maxime.debaugnies"
cd "$ROOT"

PID_FILE="lead_scheduler.pid"
LOCK_FILE="lead_scheduler.lock"
LOG_FILE="logs/lead_scheduler.log"
WATCHDOG_LOG="logs/watchdog_lead_scheduler.log"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$WATCHDOG_LOG"; }

start_scheduler() {
    rm -f "$LOCK_FILE"
    setsid nohup python3 lead_scheduler.py >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    log "scheduler started (PID $(cat "$PID_FILE"))"
}

while true; do
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE" 2>/dev/null || true)
        if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
            : # alive, silence — log toutes les 10 min via le compteur ci-dessous
        else
            log "scheduler dead (PID $PID), restarting..."
            rm -f "$PID_FILE"
            start_scheduler
        fi
    else
        log "no PID file, starting scheduler..."
        start_scheduler
    fi
    sleep 60
done
