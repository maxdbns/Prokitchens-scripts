# Passation — Appels d'offres (tenders) et veille (news)

Dernière mise à jour : 25/11/2026. Aucune valeur de secret dans ce document : uniquement des noms.

## 1. Vue d'ensemble

| Module | Quoi | Quand (UTC) | Où ça tourne |
|---|---|---|---|
| Tenders | Collecte de 22 sources d'appels d'offres, classement par catégorie, rapprochement avec les leads | 03:07 chaque jour | GitHub Actions `daily-tenders.yml` (repo `Prokitchens-scripts`) |
| Briefing | Notifications et résumé du matin, lus en base | 04:00 chaque jour | Vercel cron `/api/cron/daily` (app `prokitchens-app`) |
| News | Veille sectorielle : 14 requêtes Google News RSS + 5 flux directs, tags, dédoublonnage, matching leads, email des « articles chauds » | 08:00 chaque jour | GitHub Actions `daily-news.yml` |

Tout écrit dans Supabase. Détail complet du module tenders : `prokitchens-app/TENDERS_MODULE_STATUS.md`.

## 2. Où est le code

- Collecteur tenders : `prokitchens-app/scripts/run-tender-harvest.ts`, adaptateurs dans `src/lib/tender-sources/` (un fichier par source, registre dans `index.ts`), tri métier dans `src/lib/tender-relevance.ts`.
- News : `scripts/ingest_news.py` (requêtes `QUERIES` et flux `DIRECT_FEEDS` en haut du fichier).
- Alerte d'échec de workflow : `scripts/notify_workflow_failure.py`.
- Le workflow tenders récupère l'app (repo privé `Prokitchens`) via une clé SSH.

## 3. Secrets et variables (noms uniquement)

**GitHub, repo `Prokitchens-scripts` (Settings → Secrets and variables → Actions)**
`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `RESEND_API_KEY`, `NOTIFICATION_EMAIL_TO`, `PROKITCHENS_APP_SSH_KEY`, `SUPABASE_DB_PASSWORD`, `CRON_SECRET`, `GOOGLE_PLACES_API_KEY`, `INSEE_API_KEY`, `INPI_USERNAME`, `INPI_PASSWORD`, `UNEMPLACEMENT_EMAIL`, `UNEMPLACEMENT_PASSWORD`, `NEXT_PUBLIC_SITE_URL`.

**Vercel (projet de l'app)**
`NEXT_PUBLIC_SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `RESEND_API_KEY`, `NOTIFICATION_EMAIL_TO`, optionnellement `NOTIFICATION_EMAIL_FROM`.

**Local** : `prokitchens-app/.env` (ignoré par git).

## 4. Emails et alertes

- Destinataires : `NOTIFICATION_EMAIL_TO`, une ou plusieurs adresses séparées par des virgules. Lu par `ingest_news.py`, `notify_workflow_failure.py`, `send_growth_alerts.py` et l'app (`src/lib/api/resend.ts`).
- Expéditeur : `NOTIFICATION_EMAIL_FROM` si défini, sinon `ProKitchens <onboarding@resend.dev>`.
- **Piège Resend** : l'expéditeur de test `onboarding@resend.dev` ne livre qu'à l'adresse du propriétaire du compte Resend. Pour qu'une autre personne reçoive les emails, soit elle possède le compte Resend (et sa clé `RESEND_API_KEY`), soit on vérifie un domaine dans Resend et on renseigne `NOTIFICATION_EMAIL_FROM`.
- Une alerte « Échec » part quand un job plante. Si `RESEND_API_KEY` ou `NOTIFICATION_EMAIL_TO` manque, elle est ignorée sans erreur : un échec peut passer inaperçu.
- Les workflows ne transmettent pas encore `NOTIFICATION_EMAIL_FROM` : à ajouter dans leur bloc `env` si un domaine est vérifié.

## 5. Relancer et tester à la main

```bash
# Run manuel en CI (dry-run, une source)
gh workflow run daily-tenders.yml -R maxdbns/Prokitchens-scripts -f dry_run=true -f sources=decp
gh workflow run daily-news.yml    -R maxdbns/Prokitchens-scripts

# En local (Node 20 requis, le node par défaut du serveur est en v16)
export PATH=$HOME/.nvm/versions/node/v20.20.2/bin:$PATH
cd prokitchens-app
npm test
npx tsx scripts/run-tender-harvest.ts --dry-run
npx tsx scripts/run-tender-harvest.ts --source=place,sncf-placedelagare --dry-run
set -a; . ./.env; set +a; python3 ../scripts/ingest_news.py --dry-run
```

Journal des passages tenders : table `tender_source_runs` (une ligne par source et par run, avec `status` et `error`). C'est le premier endroit à regarder si une source semble muette.

Appliquer une migration SQL : workflow manuel `apply-migration.yml`, avec le chemin du fichier en entrée.

## 6. Pièges connus

- Supabase plafonne les réponses REST à 1000 lignes : toujours paginer.
- Chaque nouveau faux positif du tri tenders doit être ajouté en test dans `prokitchens-app/src/lib/tender-sources/__tests__/relevance.test.ts` avant de modifier les règles.
- DECP : la ressource a changé de nom (`decp.csv.gz`) ; elle était en panne du 06/11 au 24/11/2026.
- Paris Commerces : seule la première page est lue (environ 14 locaux).
- Non couverts : plateformes Atexo sans flux RSS, sources payantes (achats-publics, france-tenders).
- Google News RSS peut changer de format ou limiter les requêtes : surveiller le nombre d'articles ingérés par jour.

## 7. À faire à la passation

1. Transférer GitHub, Vercel, Supabase (dans cet ordre) vers les espaces du nouveau propriétaire.
2. Après le transfert GitHub : régénérer la clé de déploiement SSH du repo `Prokitchens`, mettre à jour `PROKITCHENS_APP_SSH_KEY`, recréer les secrets du repo.
3. Régénérer la clé secrète Supabase (l'ancienne figure dans l'historique public de `Prokitchens-scripts`), puis la mettre à jour dans GitHub, Vercel et `.env`.
4. Mettre `NOTIFICATION_EMAIL_TO` (GitHub et Vercel) sur la nouvelle adresse, et régler le point Resend du §4.
5. Supprimer les fichiers de clés en clair du dossier de travail : `cle_sync.txt`, `KEYS.txt`, `cles-prokitchens-short-term.txt`.
6. Lancer une fois à la main les deux workflows (§5) et vérifier qu'ils passent.
