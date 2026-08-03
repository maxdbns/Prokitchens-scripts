#!/usr/bin/env bash
set -e
cd /zpool/one/maxime.debaugnies

for PID_FILE in ai_request_processor.pid watchdog_ai_processor.pid; do
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE" 2>/dev/null || true)
        if [ -n "$PID" ]; then
            kill "$PID" 2>/dev/null && echo "Killed PID $PID ($PID_FILE)" || true
        fi
        rm -f "$PID_FILE"
    fi
done

rm -f ai_request_processor.lock
echo "AI Processor arrete."
