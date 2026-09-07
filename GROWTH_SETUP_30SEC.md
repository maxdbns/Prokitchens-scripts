# ⚡ Setup Growth Tracking

## Situation actuelle

Le système de détection "hyperscale QSR" est prêt et testé :
- ✅ Google Trends : vérifié fonctionnel en direct
- ✅ Scoring de vélocité (croissance CA + ouvertures relatives + trends + avis) : basé sur des données déjà fiables
- ✅ Alertes email hebdo : prêtes
- ❌ LinkedIn scraper : **retiré**, vérifié non-fonctionnel (LinkedIn bloque tout accès automatisé, même sur pages publiques — testé en direct, échec systématique). Le remplacer aurait fait tourner un job pour rien chaque heure.

Il manque juste les colonnes de tracking dans Supabase.

## Option recommandée (une fois pour toutes) — 1 commande, 0 exposition du mot de passe

Pour que je puisse appliquer **cette migration et toutes les futures** sans jamais te redemander de coller du SQL à la main, il faut un secret GitHub que je n'ai jamais eu : `SUPABASE_DB_PASSWORD` (le mot de passe Postgres du projet — différent de la clé API service_role qu'on utilise déjà).

**Dans ton propre terminal** (jamais dans ce chat, pour ne pas exposer le mot de passe) :
```bash
gh secret set SUPABASE_DB_PASSWORD -R maxdbns/Prokitchens-scripts
```
Ça te demande de coller le mot de passe (le même que celui du dashboard Supabase → Project Settings → Database → Connection string). Une fois fait, dis-le-moi et je lance la migration + je vérifie tout moi-même.

*(Ce mot de passe, une fois stocké comme secret GitHub, ne sert QUE dans les workflows CI — il ne transite jamais par le chat.)*

## Option immédiate (si tu préfères ne pas faire ça maintenant) — 30 secondes

1. Va à: https://supabase.com/dashboard/projects → ProKitchens → **SQL Editor**
2. Copie-colle et Run:

```sql
ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS google_trend_score float DEFAULT 0.0;
ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS google_trend_keywords text[] DEFAULT ARRAY[]::text[];
ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS google_trend_last_checked timestamp;
ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS growth_velocity_score float DEFAULT 0.0;
ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS growth_velocity_components jsonb DEFAULT '{}'::jsonb;
ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS growth_velocity_updated_at timestamp;
ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS alert_growth_momentum boolean DEFAULT false;
ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS alert_last_sent timestamp;

CREATE INDEX IF NOT EXISTS idx_leads_growth_velocity_score ON public.leads (growth_velocity_score DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_leads_google_trend_score ON public.leads (google_trend_score DESC NULLS LAST);

CREATE OR REPLACE VIEW top_growth_leads AS
SELECT id, nom, ville, region, growth_velocity_score,
       croissance_ca, sites_ouverts_12m, nb_etablissements,
       google_trend_score, score as original_score,
       CASE
         WHEN growth_velocity_score > 0.8 THEN 'hyper-growth'
         WHEN growth_velocity_score > 0.5 THEN 'strong-growth'
         WHEN growth_velocity_score > 0.3 THEN 'growth'
         ELSE 'stable'
       END as growth_category,
       updated_at
FROM public.leads
WHERE growth_velocity_score > 0.3
ORDER BY growth_velocity_score DESC;
```

3. Dis-moi que c'est fait, je lance immédiatement `recalc_growth_score.py` et `google_trends_enrich.py` pour vérifier que tout fonctionne de bout en bout.

---

## Automatisation (une fois les colonnes en place)

| Tâche | Fréquence | Heure |
|-------|-----------|-------|
| Google Trends | Daily | 06:30 UTC |
| Growth Score recalc | Daily | 22:45 UTC |
| **Weekly alerts** | Lundi | 08:00 UTC |
