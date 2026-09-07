# ⚡ Setup Growth Tracking (30 secondes)

## Le système est prêt, il faut juste ajouter les colonnes Supabase

### À faire MAINTENANT:

1. Va à: https://supabase.com/dashboard/projects
2. Sélectionne ProKitchens → **SQL Editor**
3. Copie-colle **TOUS ces statements** d'un coup:

```sql
ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS linkedin_company_url text;
ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS linkedin_followers int DEFAULT 0;
ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS linkedin_followers_30d_change int DEFAULT 0;
ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS linkedin_hires_3m int DEFAULT 0;
ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS linkedin_last_checked timestamp;
ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS google_trend_score float DEFAULT 0.0;
ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS google_trend_keywords text[] DEFAULT ARRAY[]::text[];
ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS google_trend_last_checked timestamp;
ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS growth_velocity_score float DEFAULT 0.0;
ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS growth_velocity_components jsonb DEFAULT '{}'::jsonb;
ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS growth_velocity_updated_at timestamp;
ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS alert_growth_momentum boolean DEFAULT false;
ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS alert_last_sent timestamp;

CREATE INDEX IF NOT EXISTS idx_leads_growth_velocity_score ON public.leads (growth_velocity_score DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_leads_linkedin_followers ON public.leads (linkedin_followers DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_leads_google_trend_score ON public.leads (google_trend_score DESC NULLS LAST);
```

4. Clique **"Run"**

5. Appelle cette requête pour vérifier:
```sql
SELECT COUNT(*) FROM public.leads WHERE linkedin_followers IS NOT NULL OR growth_velocity_score > 0;
```

---

## Après, c'est automatique 🤖

| Tâche | Fréquence | Heure |
|-------|-----------|-------|
| LinkedIn scraper | Hourly | Chaque heure |
| Google Trends | Daily | 06:30 UTC |
| Growth Score recalc | Daily | 22:45 UTC |
| **Weekly alerts** | Lundi | 08:00 UTC |

Tu recevras chaque lundi matin un email avec le top 20 des hyper-growth QSR.

---

## ✅ Setup Checklist:

- [ ] Ajouter colonnes en Supabase (30 sec)
- [ ] Vérifier: query SELECT retourne > 0
- [ ] Attendre lundi 08:00 UTC pour le premier email

**Voilà. C'est tout.**
