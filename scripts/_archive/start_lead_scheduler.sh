#!/usr/bin/env bash
# Lance le watchdog + scheduler dans une session indépendante (setsid).
# Survit à la fermeture du terminal grâce à setsid (nouvelle session kernel).
set -e

ROOT="/zpool/one/maxime.debaugnies"
cd "$ROOT"

WATCHDOG_PID_FILE="watchdog_lead_scheduler.pid"
SCHEDULER_PID_FILE="lead_scheduler.pid"

# Vérifie si le watchdog tourne déjà
if [ -f "$WATCHDOG_PID_FILE" ]; then
    OLD_PID=$(cat "$WATCHDOG_PID_FILE" 2>/dev/null || true)
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo "Watchdog déjà actif (PID $OLD_PID)."
        # Vérifie aussi le scheduler
        if [ -f "$SCHEDULER_PID_FILE" ]; then
            SCHED_PID=$(cat "$SCHEDULER_PID_FILE" 2>/dev/null || true)
            if [ -n "$SCHED_PID" ] && kill -0 "$SCHED_PID" 2>/dev/null; then
                echo "Scheduler actif (PID $SCHED_PID)."
            else
                echo "Scheduler mort — le watchdog va le relancer sous 60s."
            fi
        fi
        echo "Arrêt : ./stop_lead_scheduler.sh"
        exit 0
    fi
fi

# Nettoyage
rm -f "$WATCHDOG_PID_FILE" "$SCHEDULER_PID_FILE" lead_scheduler.lock

echo "Démarrage du watchdog (setsid — survit à la fermeture du terminal)..."
setsid nohup bash watchdog_lead_scheduler.sh >> logs/watchdog_lead_scheduler.log 2>&1 &
WATCHDOG_PID=$!
echo "$WATCHDOG_PID" > "$WATCHDOG_PID_FILE"

# Attend que le watchdog démarre le scheduler
sleep 3
if [ -f "$SCHEDULER_PID_FILE" ]; then
    SCHED_PID=$(cat "$SCHEDULER_PID_FILE")
    echo "Watchdog lancé (PID $WATCHDOG_PID), scheduler lancé (PID $SCHED_PID)"
else
    echo "Watchdog lancé (PID $WATCHDOG_PID), scheduler démarrera sous 60s"
fi
echo "Logs watchdog : logs/watchdog_lead_scheduler.log"
echo "Logs scheduler : logs/lead_scheduler.log"
echo "Arrêt : ./stop_lead_scheduler.sh"
