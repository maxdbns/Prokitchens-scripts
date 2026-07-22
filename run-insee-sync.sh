#!/usr/bin/env bash
# Lance le sync INSEE TypeScript (run-insee-sync.ts) avec Node 20.
# Utilisé par lead_scheduler.py à la place du daily_sirene_delta.py obsolète.
set -e

cd /zpool/one/maxime.debaugnies/prokitchens-app

# Charger les variables d'environnement
set -a
source .env
set +a

# Node 20 requis pour Supabase Realtime
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
nvm use 20 >/dev/null 2>&1

# Lancer le script TS
exec npx tsx scripts/run-insee-sync.ts
