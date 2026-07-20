-- Amélioration du scoring ProKitchens
-- Ajoute les colonnes de score si elles n'existent pas, puis recalcule tous les scores.

-- ─── Colonnes existantes à conserver ───
-- score_ca, score_sites, score_croissance (déjà présents)

-- ─── Ajout des nouvelles colonnes de score ───
ALTER TABLE leads
  ADD COLUMN IF NOT EXISTS telephone text,
  ADD COLUMN IF NOT EXISTS site_web text,
  ADD COLUMN IF NOT EXISTS email text,
  ADD COLUMN IF NOT EXISTS nb_tenders integer DEFAULT 0,
  ADD COLUMN IF NOT EXISTS nb_tender_notices integer DEFAULT 0,
  ADD COLUMN IF NOT EXISTS is_chaine boolean DEFAULT false,
  ADD COLUMN IF NOT EXISTS score_contact smallint DEFAULT 0,
  ADD COLUMN IF NOT EXISTS score_intention smallint DEFAULT 0,
  ADD COLUMN IF NOT EXISTS score_chaine smallint DEFAULT 0,
  ADD COLUMN IF NOT EXISTS score_total smallint DEFAULT 0;

-- ─── Score contact (qualité des données de contact) ───
-- 0-25 points : téléphone, site web, email
UPDATE leads SET
  score_contact =
    (CASE WHEN telephone IS NOT NULL AND telephone <> '' THEN 10 ELSE 0 END)
    + (CASE WHEN site_web IS NOT NULL AND site_web <> '' THEN 8 ELSE 0 END)
    + (CASE WHEN email IS NOT NULL AND email <> '' THEN 7 ELSE 0 END);

-- ─── Score CA (max 30) ───
UPDATE leads SET
  score_ca = CASE
    WHEN chiffre_affaires IS NOT NULL AND chiffre_affaires > 0 THEN
      CASE
        WHEN chiffre_affaires >= 5000000 THEN 30
        WHEN chiffre_affaires >= 2000000 THEN 25
        WHEN chiffre_affaires >= 1000000 THEN 20
        WHEN chiffre_affaires >= 500000 THEN 15
        WHEN chiffre_affaires >= 100000 THEN 10
        ELSE 5
      END
    ELSE 0
  END;

-- ─── Score sites (max 35) ───
UPDATE leads SET
  score_sites = CASE
    WHEN chiffre_affaires IS NOT NULL AND chiffre_affaires > 0 THEN
      CASE
        WHEN nb_etablissements >= 10 THEN 35
        WHEN nb_etablissements >= 5 THEN 30
        WHEN nb_etablissements >= 3 THEN 20
        WHEN nb_etablissements >= 2 THEN 12
        ELSE 0
      END
    ELSE
      ROUND(CASE
        WHEN nb_etablissements >= 10 THEN 35
        WHEN nb_etablissements >= 5 THEN 30
        WHEN nb_etablissements >= 3 THEN 20
        WHEN nb_etablissements >= 2 THEN 12
        ELSE 0
      END::numeric / 35.0 * 60.0)::smallint
  END;

-- ─── Score croissance (max 30) ───
UPDATE leads SET
  score_croissance = CASE
    WHEN chiffre_affaires IS NOT NULL AND chiffre_affaires > 0 AND croissance_ca IS NOT NULL THEN
      (CASE WHEN croissance_ca >= 30 THEN 15 WHEN croissance_ca >= 15 THEN 12 WHEN croissance_ca >= 5 THEN 8 WHEN croissance_ca >= 0 THEN 4 ELSE 0 END)
      + (CASE WHEN COALESCE(sites_ouverts_12m,0) >= 3 THEN 15 WHEN COALESCE(sites_ouverts_12m,0) >= 2 THEN 12 WHEN COALESCE(sites_ouverts_12m,0) >= 1 AND derniere_ouverture IS NOT NULL AND derniere_ouverture::date >= CURRENT_DATE - INTERVAL '6 months' THEN 8 WHEN COALESCE(sites_ouverts_12m,0) >= 1 THEN 4 ELSE 0 END)
      + (CASE WHEN nb_etablissements >= 3 AND derniere_ouverture IS NOT NULL AND derniere_ouverture::date >= CURRENT_DATE - INTERVAL '6 months' THEN 5 WHEN nb_etablissements >= 2 AND derniere_ouverture IS NOT NULL AND derniere_ouverture::date >= CURRENT_DATE - INTERVAL '12 months' THEN 3 ELSE 0 END)
    WHEN chiffre_affaires IS NULL OR chiffre_affaires <= 0 THEN
      ROUND((
        (CASE WHEN COALESCE(sites_ouverts_12m,0) >= 3 THEN 15 WHEN COALESCE(sites_ouverts_12m,0) >= 2 THEN 12 WHEN COALESCE(sites_ouverts_12m,0) >= 1 AND derniere_ouverture IS NOT NULL AND derniere_ouverture::date >= CURRENT_DATE - INTERVAL '6 months' THEN 8 WHEN COALESCE(sites_ouverts_12m,0) >= 1 THEN 4 ELSE 0 END)
        + (CASE WHEN nb_etablissements >= 3 AND derniere_ouverture IS NOT NULL AND derniere_ouverture::date >= CURRENT_DATE - INTERVAL '6 months' THEN 5 WHEN nb_etablissements >= 2 AND derniere_ouverture IS NOT NULL AND derniere_ouverture::date >= CURRENT_DATE - INTERVAL '12 months' THEN 3 ELSE 0 END)
      )::numeric / 20.0 * 40.0)::smallint
    ELSE
      ROUND((
        (CASE WHEN COALESCE(sites_ouverts_12m,0) >= 3 THEN 15 WHEN COALESCE(sites_ouverts_12m,0) >= 2 THEN 12 WHEN COALESCE(sites_ouverts_12m,0) >= 1 AND derniere_ouverture IS NOT NULL AND derniere_ouverture::date >= CURRENT_DATE - INTERVAL '6 months' THEN 8 WHEN COALESCE(sites_ouverts_12m,0) >= 1 THEN 4 ELSE 0 END)
        + (CASE WHEN nb_etablissements >= 3 AND derniere_ouverture IS NOT NULL AND derniere_ouverture::date >= CURRENT_DATE - INTERVAL '6 months' THEN 5 WHEN nb_etablissements >= 2 AND derniere_ouverture IS NOT NULL AND derniere_ouverture::date >= CURRENT_DATE - INTERVAL '12 months' THEN 3 ELSE 0 END)
      )::numeric / 20.0 * 35.0)::smallint
  END;

-- ─── Score intention (signaux d'achat) ───
-- 0-25 points : croissance récente, ouvertures récentes, appels d'offres, changement de dirigeant
UPDATE leads SET
  score_intention =
    (CASE WHEN croissance_ca >= 30 THEN 10
          WHEN croissance_ca >= 15 THEN 7
          WHEN croissance_ca >= 5 THEN 4
          ELSE 0 END)
    + (CASE WHEN COALESCE(sites_ouverts_12m, 0) >= 3 THEN 8
            WHEN COALESCE(sites_ouverts_12m, 0) >= 1 THEN 4
            ELSE 0 END)
    + (CASE WHEN COALESCE(nb_tenders, 0) >= 1 THEN 5
            ELSE 0 END)
    + (CASE WHEN COALESCE(nb_tender_notices, 0) >= 1 THEN 2
            ELSE 0 END);

-- ─── Score chaîne / franchise (0-20) ───
-- Plus un lead a de sites et plus le nom ressemble à une chaîne, plus c'est intéressant
UPDATE leads SET
  score_chaine =
    (CASE WHEN nb_etablissements >= 10 THEN 15
          WHEN nb_etablissements >= 5 THEN 12
          WHEN nb_etablissements >= 3 THEN 8
          WHEN nb_etablissements >= 2 THEN 4
          ELSE 0 END)
    + (CASE WHEN is_chaine IS TRUE THEN 5 ELSE 0 END);

-- ─── Score total ───
-- Poids : CA 30%, sites 25%, croissance 20%, contact 10%, intention 10%, chaîne 5%
UPDATE leads SET
  score_total = ROUND((
    COALESCE(score_ca, 0) * 0.30
    + COALESCE(score_sites, 0) * 0.25
    + COALESCE(score_croissance, 0) * 0.20
    + COALESCE(score_contact, 0) * 0.10
    + COALESCE(score_intention, 0) * 0.10
    + COALESCE(score_chaine, 0) * 0.05
  )::numeric)::smallint;

-- ─── Mise à jour du score legacy pour compatibilité ───
UPDATE leads SET score = score_total;
