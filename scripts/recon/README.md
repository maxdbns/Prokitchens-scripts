# Recon UnEmplacement — archives

Scripts d'exploration ayant servi à découvrir l'API interne UnEmplacement
(juillet 2026). Conservés à titre documentaire — **ne plus utiliser en
production**, le collecteur officiel est `scripts/collect_unemplacement_demandes.py`.

## Ce que la recon a établi

- Pas besoin de scraping Playwright : le front web appelle une API JSON directe.
- Auth : Firebase `signInWithPassword` via
  `https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=<FIREBASE_API_KEY>`
  (clé API publique embarquée dans le site) → retourne un `idToken` JWT,
  à passer en `Authorization: Bearer`.
- Endpoint principal : `POST https://api.app.unemplacement.com/member_api/fetch_prospections`
  - body : `state=Île-de-France`, `prospectionType=1`, pagination 20/page.
- Identifiants : compte de service (paul.bonnard@cloudkitchens.com), stockés dans
  `prokitchens-app/.env` (`UNEMPLACEMENT_EMAIL` / `UNEMPLACEMENT_PASSWORD`).
  Ne jamais les committer.

## Rôle des scripts archivés

- `recon_unemplacement.py` / `recon_unemplacement_app.py` : capture du trafic
  réseau du site pour identifier l'API.
- `recon_recherche_detail.py` / `recon_card_dom.py` : structure des recherches
  et des cartes (champs disponibles).
- `recon_enseigne_url.py` : résolution des URLs/noms d'enseignes.
- `test_unemplacement_api.py` / `test_map_all.py` : premiers appels d'API de
  validation.
- `capture_comments_endpoint.py` : découverte de l'endpoint des commentaires
  (utilisé par `enrich_commentaires.py`).
