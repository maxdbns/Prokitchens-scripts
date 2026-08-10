#!/bin/bash
# Watchdog : vérifie toutes les 5 min que le runner et le scheduler tournent.
# Si l'un est mort, le relance. Tourne en boucle détachée (survit à la session).

ROOT="/zpool/one/maxime.debaugnies"
LOGS="$ROOT/logs"
mkdir -p "$LOGS"

while true; do
    # Runner GitHub Actions
    if ! pgrep -f "Runner.Listener" > /dev/null; then
        echo "[$(date)] ALERTE: Runner mort, relance..." >> "$LOGS/watchdog_services.log"
        cd "$ROOT/actions-runner"
        setsid nohup ./run.sh >> "$LOGS/actions-runner.log" 2>&1 &
        disown
    fi

    # Lead Scheduler
    if ! pgrep -f "lead_scheduler.py" > /dev/null; then
        echo "[$(date)] ALERTE: Scheduler mort, relance..." >> "$LOGS/watchdog_services.log"
        cd "$ROOT"
        setsid nohup python3 lead_scheduler.py >> "$LOGS/lead_scheduler.log" 2>&1 &
        disown
    fi

    sleep 300  # 5 minutes
done
