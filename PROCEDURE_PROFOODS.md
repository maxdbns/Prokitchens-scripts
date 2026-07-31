# ProFoods — Procédure d'exécution

## État actuel (2026-07-30)

- Module ProFoods déployé sur https://prokitchens-three.vercel.app/profoods
- 155 biens ProFood Properties + 727 demandes UnEmplacement IDF en production
- ~28 000 matches calculés en temps réel par l'API (score ≥ 1)
- Collecte et enrichissements entièrement automatisés — plus d'intervention quotidienne

## Architecture de la chaîne quotidienne

| Heure | Quoi | Où |
|---|---|---|
| Toutes les 15 min | Sync biens : Google Sheets → site | Apps Script (déclencheur minuteur) |
| 05:30 UTC | Collecte demandes UnEmplacement IDF → filtre food → ingestion | Cron Vercel `run-step?step=profoods_sync` |
| 07:00 | Enrichissement noms d'enseigne des demandes | `lead_scheduler` local → `scripts/enrich_enseignes.py` |
| 07:30 | Enrichissement commentaires des recherches (critères, zones) | `lead_scheduler` local → `scripts/enrich_commentaires.py` |

Le matching biens × demandes n'est **pas** persisté : il est recalculé en
temps réel par `/api/profoods/matching` à chaque requête.

## Points techniques clés

- **UnEmplacement** : pas de scraping Playwright. API JSON directe découverte
  par recon réseau (juillet 2026), documentée dans `scripts/recon/README.md`.
  - Auth : Firebase `signInWithPassword` (clé API publique du site) → JWT Bearer
  - Endpoint : `POST api.app.unemplacement.com/member_api/fetch_prospections`
    (state=Île-de-France, prospectionType=1, pagination 20/page)
- **Biens** : la source de vérité est le Google Sheet ProFoods ; l'Apps Script
  `scripts/profoods_sheets_sync_appscript.js` le pousse toutes les 15 min vers
  `/api/profoods/biens/sync` (auth `PROFOODS_SHEETS_SECRET` côté Vercel).
- **Enrichissements** : n'enrichissent que les nouvelles recherches (pas de
  re-traitement de l'historique chaque jour).

## Fichiers importants

- Collecteur demandes (manuel / debug) : `scripts/collect_unemplacement_demandes.py`
- Enrichissements quotidiens : `scripts/enrich_enseignes.py`, `scripts/enrich_commentaires.py`
- Push des biens (secours, hors Sheets) : `scripts/push_biens_profoods.py`
- Apps Script de sync Sheets : `scripts/profoods_sheets_sync_appscript.js`
- Archives de recon API : `scripts/recon/`
- Code de l'app : `prokitchens-app/`

## Variables d'environnement

Dans `prokitchens-app/.env` (chargé automatiquement par `lead_scheduler`) :

```
UNEMPLACEMENT_EMAIL=...      # compte de service — ne jamais committer
UNEMPLACEMENT_PASSWORD=...
```

Côté Vercel : `PROFOODS_SHEETS_SECRET`, `CRON_SECRET`, plus les clés
Supabase/Resend habituelles.

## Commandes utiles

```bash
# Collecte manuelle des demandes (dry-run, sans push)
set -a && source prokitchens-app/.env && set +a
python3 scripts/collect_unemplacement_demandes.py

# Collecte + push vers la production
python3 scripts/collect_unemplacement_demandes.py --push

# Repousser uniquement les biens (si la sync Sheets est en panne)
python3 scripts/push_biens_profoods.py
```

## Vérifications rapides en production

```bash
# Nombre de biens
curl -s "https://prokitchens-three.vercel.app/api/profoods/biens?per_page=1" | python3 -c "import sys,json; print(json.load(sys.stdin)['total'])"

# Nombre de demandes
curl -s "https://prokitchens-three.vercel.app/api/profoods/demandes?per_page=1" | python3 -c "import sys,json; print(json.load(sys.stdin)['total'])"

# Nombre de matches
curl -s "https://prokitchens-three.vercel.app/api/profoods/matching?min_score=1&limit=1" | python3 -c "import sys,json; print(json.load(sys.stdin)['total'])"
```

## Supervision

- Scheduler local : `lead_scheduler.py` (PID dans `lead_scheduler.pid`,
  relancé automatiquement par `watchdog_lead_scheduler.sh`)
- Logs : `logs/lead_scheduler.log` et `logs/watchdog_lead_scheduler.log`
- Si le scheduler est mort : `./start_lead_scheduler.sh` puis relancer le
  watchdog avec `nohup ./watchdog_lead_scheduler.sh &`
- Les tâches `vercel_notifications` (9h) et `revalidate_google` (10h30)
  nécessitent `CRON_SECRET` dans `prokitchens-app/.env` — à copier depuis les
  env vars Vercel si absent.
