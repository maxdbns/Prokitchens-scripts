# ProFoods — Procédure d'exécution finale

## État actuel (2026-07-28)

- Module ProFoods déployé sur https://prokitchens-three.vercel.app/profoods
- 155 biens ProFoods déjà injectés en production
- Tables Supabase créées et vides côté demandes clients
- Il ne manque plus que les credentials UnEmplacement.com pour lancer le scraping

## Fichiers importants

- Notebook de scraping : `notebooks/04_scraping_unemplacement_matching.ipynb`
- CSV nettoyé des biens : `data/biens_profoods.csv`
- Script de push des biens : `scripts/push_biens_profoods.py`
- Code de l'app : `prokitchens-app/`

## Variables d'environnement à définir avant de lancer le notebook

```bash
export UNEMPLACEMENT_EMAIL="ton-email@example.com"
export UNEMPLACEMENT_PASSWORD="ton-mot-de-passe"
export PROFOODS_API_URL="https://prokitchens-three.vercel.app/api/profoods/ingest"
export PUSH_TO_PROKITCHENS="1"
```

Optionnellement :

```bash
export PATH_CSV_PROFOODS="/zpool/one/maxime.debaugnies/data/biens_profoods.csv"
export PATH_CSV_PROFOODS_SOURCE="/zpool/one/maxime.debaugnies/profoods/*.csv"
export PLAYWRIGHT_HEADLESS="true"
export PLAYWRIGHT_SLOW_MO="150"
```

## Commande pour relancer le notebook en une seule passe (Jupyter + nbconvert)

```bash
cd /zpool/one/maxime.debaugnies
export PATH="/zpool/one/maxime.debaugnies/.nvm/versions/node/v20.20.2/bin:$PATH"
export UNEMPLACEMENT_EMAIL="..."
export UNEMPLACEMENT_PASSWORD="..."
export PROFOODS_API_URL="https://prokitchens-three.vercel.app/api/profoods/ingest"
export PUSH_TO_PROKITCHENS="1"

jupyter nbconvert --to notebook --execute notebooks/04_scraping_unemplacement_matching.ipynb --output notebooks/04_scraping_unemplacement_matching_executed.ipynb
```

## Commande pour repousser uniquement les biens (si besoin)

```bash
cd /zpool/one/maxime.debaugnies
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

## Notes

- Le notebook nettoie automatiquement le CSV source ProFoods s'il trouve un export brut dans `profoods/*.csv`.
- Si le CSV source change, il suffit de le remplacer dans `profoods/` et de relancer `clean_profoods_csv.py` ou le notebook.
- Le matching est recalculé en temps réel par l'API `/api/profoods/matching` ; il n'est pas persisté dans `profoods_opportunites` (table réservée à une future évolution).
