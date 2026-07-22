#!/bin/bash
# Lance le script de correction automatique des noms de leads
set -e

cd /zpool/one/maxime.debaugnies/prokitchens-app
set -a
source .env
set +a

export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
nvm use 20 2>/dev/null || nvm install 20

exec npx tsx scripts/fix-lead-names.ts
