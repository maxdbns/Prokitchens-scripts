# 🚨 PLAN CRITIQUE: Rattraper 25 jours de données manquantes

**Situation:** 0 données fraîches depuis le 13 août (25 jours)  
**Cause trouvée:** Colonne `region` manquante dans Supabase → tous les workflows GitHub Actions figés  
**Urgence:** 🔴 CRITIQUE

---

## PHASE 1: FIX SCHEMA SUPABASE (5 min)

### Étape 1.1 — Ajouter colonne `region`
1. Va sur https://supabase.com/dashboard/projects
2. Sélectionne "ProKitchens" projet
3. SQL Editor → copie-colle (PARTIE 1):
```sql
ALTER TABLE public.leads
  ADD COLUMN IF NOT EXISTS region text;

CREATE INDEX IF NOT EXISTS idx_leads_region ON public.leads (region) WHERE region IS NOT NULL;
```
4. Clique "Run" → doit dire "Success"

### Étape 1.2 — Remplir données région
1. Copie-colle (PARTIE 2) dans SQL Editor:
```sql
UPDATE public.leads SET region =
  CASE
    WHEN code_postal LIKE '75%' OR code_postal LIKE '77%' OR code_postal LIKE '78%' OR
         code_postal LIKE '91%' OR code_postal LIKE '92%' OR code_postal LIKE '93%' OR
         code_postal LIKE '94%' OR code_postal LIKE '95%' THEN 'Ile-de-France'
    WHEN code_postal LIKE '01%' OR code_postal LIKE '03%' OR code_postal LIKE '07%' OR
         code_postal LIKE '15%' OR code_postal LIKE '26%' OR code_postal LIKE '38%' OR
         code_postal LIKE '42%' OR code_postal LIKE '43%' OR code_postal LIKE '63%' OR
         code_postal LIKE '69%' OR code_postal LIKE '73%' OR code_postal LIKE '74%' THEN 'Auvergne-Rhône-Alpes'
    WHEN code_postal LIKE '04%' OR code_postal LIKE '05%' OR code_postal LIKE '06%' OR
         code_postal LIKE '13%' OR code_postal LIKE '83%' OR code_postal LIKE '84%' THEN 'Provence-Alpes-Côte d''Azur'
    WHEN code_postal LIKE '02%' OR code_postal LIKE '59%' OR code_postal LIKE '60%' OR
         code_postal LIKE '62%' OR code_postal LIKE '80%' THEN 'Hauts-de-France'
    WHEN code_postal LIKE '09%' OR code_postal LIKE '11%' OR code_postal LIKE '12%' OR
         code_postal LIKE '30%' OR code_postal LIKE '31%' OR code_postal LIKE '32%' OR
         code_postal LIKE '34%' OR code_postal LIKE '46%' OR code_postal LIKE '48%' OR
         code_postal LIKE '65%' OR code_postal LIKE '66%' OR code_postal LIKE '81%' OR code_postal LIKE '82%' THEN 'Occitanie'
    WHEN code_postal LIKE '16%' OR code_postal LIKE '17%' OR code_postal LIKE '19%' OR
         code_postal LIKE '23%' OR code_postal LIKE '24%' OR code_postal LIKE '33%' OR
         code_postal LIKE '40%' OR code_postal LIKE '47%' OR code_postal LIKE '64%' OR
         code_postal LIKE '79%' OR code_postal LIKE '86%' OR code_postal LIKE '87%' THEN 'Nouvelle-Aquitaine'
    WHEN code_postal LIKE '08%' OR code_postal LIKE '10%' OR code_postal LIKE '51%' OR
         code_postal LIKE '52%' OR code_postal LIKE '54%' OR code_postal LIKE '55%' OR
         code_postal LIKE '57%' OR code_postal LIKE '67%' OR code_postal LIKE '68%' OR code_postal LIKE '88%' THEN 'Grand Est'
    WHEN code_postal LIKE '22%' OR code_postal LIKE '29%' OR code_postal LIKE '35%' OR code_postal LIKE '56%' THEN 'Bretagne'
    WHEN code_postal LIKE '44%' OR code_postal LIKE '49%' OR code_postal LIKE '53%' OR code_postal LIKE '72%' OR code_postal LIKE '85%' THEN 'Pays de la Loire'
    WHEN code_postal LIKE '14%' OR code_postal LIKE '27%' OR code_postal LIKE '50%' OR code_postal LIKE '61%' OR code_postal LIKE '76%' THEN 'Normandie'
    WHEN code_postal LIKE '18%' OR code_postal LIKE '28%' OR code_postal LIKE '36%' OR code_postal LIKE '37%' OR code_postal LIKE '41%' OR code_postal LIKE '45%' THEN 'Centre-Val de Loire'
    WHEN code_postal LIKE '2B%' OR code_postal LIKE '20%' THEN 'Corse'
    ELSE NULL
  END
WHERE region IS NULL;
```
2. Clique "Run" (peut prendre 10-30 sec)

### Étape 1.3 — Vérifier succès
```sql
SELECT COUNT(*) as total, COUNT(region) as with_region FROM public.leads;
```
**Résultat attendu:** `total > 1000`, `with_region > 500`

### Étape 1.4 — Reset schema cache Supabase
1. Settings → Database → Schema cache
2. Clique "Reset schema cache"

---

## PHASE 2: REDÉMARRER LES WORKFLOWS (10 min)

### Étape 2.1 — Trigger tous les workflows
Va sur: https://github.com/maxdbns/Prokitchens-scripts/actions

**Pour chaque workflow (dans cet ordre):**
```
1. daily-sirene-contact.yml       (00:00 UTC - enrichissement INSEE)
2. daily-backfill-fixnames.yml    (02:00 UTC - nettoyage noms)
3. daily-google-enrich.yml        (04:00 UTC - enrichissement Google Places)
4. daily-inpi.yml                 (06:00 UTC - enrichissement INPI dirigeants)
5. daily-profoods.yml             (07:00 UTC - enrichissement ProFoods)
6. daily-news.yml                 (08:00 UTC - ingestion veille sectorielle)
```

**Pour chaque:**
- Clique sur le workflow
- Clique "Run workflow"
- Clique le bouton vert "Run workflow"
- **ATTENDS qu'il finisse** (5-15 min chacun)

### Étape 2.2 — Monitorer les exécutions
- Regarder les logs en temps réel
- **Chercher:** ✅ "SUCCÈS" ou ❌ "ERREUR"
- Si ❌ erreur → check le log complet pour déboguer

---

## PHASE 3: VÉRIFIER DANS L'APP (5 min)

### Étape 3.1 — Tester la sync
1. Ouvre l'app ProKitchens
2. Page d'accueil → clique "Synchroniser" (bouton top-right)
3. Observe le chargement:
   - **Avant:** Erreur `Could not find the 'region' column`
   - **Après:** Batch loading, chiffre final de leads mis à jour

### Étape 3.2 — Vérifier comptes
```
Avant fix:  3379 leads chargés (25 jours = STALE)
Après fix:  ? leads chargés (devraient être + nombreux, données fraîches)
```

---

## PHASE 4: RATTRAPAGE COMPLET (30-60 min)

**Une fois que les workflows redémarrent avec succès:**

### Option A: Attendre les schedules naturels (sûr mais lent)
- Workflows tournent chaque jour à l'heure prévue
- **Temps:** 25 jours de rattrapage = ~25 jours minimum
- **Problème:** Trop lent, on perd des opportunités

### Option B: Forcer un re-enrichissement complet (RECOMMANDÉ)
1. Ouvre une terminal sur cette machine
2. Lance le catchup:
```bash
cd /zpool/one/maxime.debaugnies

# Re-enrich INPI (dirigeants)
python3 inpi_enrich_dirigeants.py

# Re-enrich Google (coordonnées)
python3 google_enrich_daily.py

# Re-enrich ProFoods
python3 scripts/enrich_enseignes.py

# Ingestion news
python3 scripts/ingest_news.py
```
3. **Temps:** ~1-2 heures pour tout rattraper
4. **Résultat:** TOUTES les données à jour au 7 septembre 2026

---

## RÉSUMÉ TIMELINE

| Étape | Durée | Action |
|-------|-------|--------|
| **1. Fix schema** | 5 min | ALTER TABLE + UPDATE + reset cache |
| **2. Trigger workflows** | 10 min | Run tous les 6 workflows GitHub |
| **3. Attendre exécutions** | 30-60 min | Surveiller logs |
| **4. Vérifier app** | 5 min | Test sync + vérifier counts |
| **5. Rattrapage complet (opt)** | 60-120 min | Lance scripts Python localement |
| **TOTAL** | **2-4 heures** | Données à jour au 7 septembre ✅ |

---

## ⚠️ SI ÇA MARCHE PAS:

### Erreur: "Schema cache still stale"
- Attends 5 min après reset cache
- Rafraîchis la page de l'app (Ctrl+Shift+R hard refresh)

### Erreur: "INPI login failed"
- Les credentials INPI peuvent avoir expiré
- Va sur https://registre-national-entreprises.inpi.fr
- Teste login manuel avec les credentials
- Si échec → mettre à jour le secret GitHub

### Erreur: "Google API quota exceeded"
- Vérifier quota sur Google Cloud Console
- Possibilité que les 500 leads/jour ont atteint le max
- Réduire batch size ou augmenter quota

### Erreur: "Supabase write failed"
- Vérifier que les permissions RLS n'ont pas changé
- Tester une requête INSERT simple en SQL Editor

---

## ✅ CHECKLIST FINAL

- [ ] Colonne `region` ajoutée dans Supabase
- [ ] Données région remplies (~1000+ leads)
- [ ] Schema cache réinitialisé
- [ ] Tous les workflows ont tourné avec succès
- [ ] App sync fonctionne sans erreur
- [ ] Counts de leads augmentés (nouvelles données)
- [ ] Logs d'enrichissement montrent ✅ SUCCÈS
- [ ] Commit la fix vers GitHub

---

**Mis à jour:** 2026-09-07  
**Urgence:** 🔴 CRITIQUE — 25 jours de données manquantes
