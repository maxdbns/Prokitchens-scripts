ALTER TABLE leads
  ADD COLUMN resultat_net bigint,
  ADD COLUMN date_cloture_bilan text,
  ADD COLUMN enriched_inpi boolean DEFAULT false;
