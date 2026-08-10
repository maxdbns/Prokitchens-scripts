#!/bin/bash
# Démarre le runner GitHub Actions et le scheduler Python
# en les détachant complètement de la session (survit à la fermeture).

ROOT="/zpool/one/maxime.debaugnies"
LOGS="$ROOT/logs"
mkdir -p "$LOGS"

# --- GitHub Actions Runner ---
if pgrep -f "Runner.Listener" > /dev/null; then
    echo "[$(date)] Runner déjà en cours"
else
    cd "$ROOT/actions-runner"
    setsid nohup ./run.sh >> "$LOGS/actions-runner.log" 2>&1 &
    disown
    echo "[$(date)] Runner démarré (PID $!)"
fi

# --- Lead Scheduler ---
if pgrep -f "lead_scheduler.py" > /dev/null; then
    echo "[$(date)] Scheduler déjà en cours"
else
    cd "$ROOT"
    setsid nohup python3 lead_scheduler.py >> "$LOGS/lead_scheduler.log" 2>&1 &
    disown
    echo "[$(date)] Scheduler démarré (PID $!)"
fi
