#!/usr/bin/env bash
# Arrête le scheduler et son watchdog.
set -e

ROOT="/zpool/one/maxime.debaugnies"
cd "$ROOT"

for PID_FILE in lead_scheduler.pid watchdog_lead_scheduler.pid; do
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE" 2>/dev/null || true)
        if [ -n "$PID" ]; then
            kill "$PID" 2>/dev/null || true
        fi
        rm -f "$PID_FILE"
    fi
done

rm -f lead_scheduler.lock
echo "Scheduler et watchdog arrêtés."
