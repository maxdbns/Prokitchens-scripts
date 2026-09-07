# ⚡ 30-SECOND FIX: Add `region` column to ProKitchens

**COPIE-COLLE CES 2 BLOCS DIRECTEMENT DANS SUPABASE SQL EDITOR**

---

## 🌐 ÉTAPE 1 (10 secondes)
Va à: https://supabase.com/dashboard/projects

Sélectionne le projet ProKitchens → SQL Editor

---

## 1️⃣ COPIE-COLLE CE BLOC DANS L'ÉDITEUR SQL:

```sql
ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS region text;
CREATE INDEX IF NOT EXISTS idx_leads_region ON public.leads (region) WHERE region IS NOT NULL;
NOTIFY pgrst, 'reload schema';
```

**Clique "Run"** → Doit afficher "Success"

*(la ligne `NOTIFY pgrst` force PostgREST à recharger immédiatement le schéma — sinon ça se fait automatiquement tout seul en quelques secondes/minutes)*

---

##  2️⃣ ATTENDS 5 SEC, puis COPIE-COLLE CE DEUXIÈME BLOC:

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

**Clique "Run"** → Doit afficher "X rows affected"

---

## 3️⃣ OPTIONAL - VÉRIFIER:

```sql
SELECT COUNT(*) as total, COUNT(region) as with_region, COUNT(DISTINCT region) as unique_regions FROM public.leads;
```

**Résultat attendu:** `total > 1000, with_region > 500, unique_regions = 13+`

---

## 4️⃣ PUIS:

- Le `NOTIFY pgrst, 'reload schema';` de l'étape 1 a déjà forcé le rechargement — pas besoin d'action supplémentaire
- (Si jamais ça persiste après 2 min: Project Settings → General → "Restart project", en dernier recours seulement)
- Ferme et re-ouvre l'app ProKitchens  
- Clique "Synchroniser"

**Résultat:** Pas d'erreur ❌→ ✅ et les données se chargent!

---

**Workflows en cours:** Daily enrichissement tournent MAINTENANT
- ✅ INPI Dirigeants
- ✅ Google Places
- ✅ ProFoods
- ✅ News
- ✅ Sirene
