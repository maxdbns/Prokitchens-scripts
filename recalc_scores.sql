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
  END,
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
  END,
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
