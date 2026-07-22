#!/usr/bin/env bash
# Lance le scheduler lead en arrière-plan (nohup) pour qu'il survive à la déconnexion.
set -e

cd /zpool/one/maxime.debaugnies

PID_FILE="lead_scheduler.pid"
LOCK_FILE="lead_scheduler.lock"

if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null || true)
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo "Scheduler déjà actif (PID $OLD_PID). Arrêtez-le d'abord :"
        echo "  kill $OLD_PID"
        exit 1
    fi
fi

echo "Démarrage du lead scheduler..."
nohup python3 lead_scheduler.py > lead_scheduler.log 2>&1 &
NEW_PID=$!
echo "$NEW_PID" > "$PID_FILE"
echo "Scheduler lancé avec PID $NEW_PID"
echo "Log : /zpool/one/maxime.debaugnies/lead_scheduler.log"
echo "Arrêt : kill $(cat $PID_FILE)"
