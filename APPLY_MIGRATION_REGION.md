# 🔧 FIX URGENT: Ajouter colonne `region` manquante

## Le Problème
- La table `leads` dans Supabase **manque la colonne `region`**
- L'app tente de charger `region` depuis le schema cache
- Erreur: `Could not find the 'region' column of 'leads' in the schema cache`
- **Résultat:** Tous les workflows GitHub Actions sont figés depuis 25 jours (13 août)

## La Solution
Appliquer la migration SQL dans Supabase SQL Editor

### ÉTAPES:

#### 1. Ouvrir Supabase SQL Editor
- Va à: https://supabase.com/dashboard/projects
- Sélectionne le projet ProKitchens
- Clique sur "SQL Editor" dans la sidebar

#### 2. Copie-colle ce SQL (PARTIE 1 - Ajouter la colonne):
```sql
ALTER TABLE public.leads
  ADD COLUMN IF NOT EXISTS region text;

CREATE INDEX IF NOT EXISTS idx_leads_region ON public.leads (region) WHERE region IS NOT NULL;
```
**Puis clique "Run"**

#### 3. Attends que ça passe (doit dire "Success"), puis copie-colle PARTIE 2 (Remplir les données):
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
**Puis clique "Run"** (cela peut prendre ~10-30 sec si 1000+ leads)

#### 4. Vérifier que ça a marché
```sql
SELECT COUNT(*) as total_leads, 
       COUNT(region) as with_region,
       COUNT(DISTINCT region) as unique_regions
FROM public.leads;
```
**Résultat attendu:** `total_leads > 1000`, `with_region > 500`, `unique_regions = 13+`

### 5. Effacer le cache Supabase
- Va dans "Settings" → "Database" → "Schema cache"
- Clique "Reset schema cache"

### 6. Relancer les workflows
- Va sur GitHub: https://github.com/maxdbns/Prokitchens-scripts/actions
- Pour chaque workflow (daily-inpi, daily-google, etc.):
  - Clique "Run workflow"
  - Clique le bouton vert "Run workflow" dans la popup

#### 7. Vérifier que ça fonctionne
- Attends 5-10 min que les premiers workflows finissent
- Vérifie: App → clic "Synchroniser" → doit charger sans erreur
- Les logs des workflows doivent montrer "✅ SUCCÈS"

## Si ça marche pas:
- [ ] Vérifie que les secrets Supabase existent dans GitHub Actions
- [ ] Vérifie que les credentials INPI n'ont pas expiré
- [ ] Envoie un mail à maxime.debaugnies@gmail.com avec le screenshot de l'erreur

