"""Enrichit profoods_demandes_clients avec les commentaires UnEmplacement.

L'endpoint member_api/prospection_details renvoie deux champs absents de la
liste : "comment" (critères détaillés) et "locations_comment" (précisions sur
les zones visées). Un appel par recherche — trop lourd pour le cron Vercel,
donc script serveur lancé quotidiennement par lead_scheduler.py.

Creds via variables d'environnement (fichier .env du repo prokitchens-app) :
  UNEMPLACEMENT_EMAIL / UNEMPLACEMENT_PASSWORD
  NEXT_PUBLIC_SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY
"""
import os
import sys
import time

import requests

ENV_PATH = "/zpool/one/maxime.debaugnies/prokitchens-app/.env"
FIREBASE_KEY = "AIzaSyBrV4UUSZyoEmUGeWYOT8JmVNCNps0-tBk"
DETAILS_URL = "https://api.app.unemplacement.com/member_api/prospection_details"
MAX_RETRIES = 4


def load_env():
    env = dict(os.environ)
    if os.path.exists(ENV_PATH):
        for line in open(ENV_PATH):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip())
    return env


def get_id_token(env):
    r = requests.post(
        f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_KEY}",
        json={
            "returnSecureToken": True,
            "email": env["UNEMPLACEMENT_EMAIL"],
            "password": env["UNEMPLACEMENT_PASSWORD"],
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["idToken"]


def main():
    full_sync = "--all" in sys.argv
    env = load_env()
    supa = env["NEXT_PUBLIC_SUPABASE_URL"].rstrip("/")
    skey = env["SUPABASE_SERVICE_ROLE_KEY"]
    sh = {"apikey": skey, "Authorization": f"Bearer {skey}"}

    token = get_id_token(env)
    ah = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Mode quotidien : seulement les recherches jamais enrichies
    # (commentaires_enrichis_at NULL = nouvelles de la dernière sync).
    # Mode --all : tout re-traiter (rattrapage). Si la colonne de suivi n'existe
    # pas encore (migration non appliquée), on bascule en mode --all legacy.
    tracking = not full_sync
    filtre = "commentaires_enrichis_at=is.null&" if tracking else ""
    rows = []
    offset = 0
    while True:
        r = requests.get(
            f"{supa}/rest/v1/profoods_demandes_clients"
            f"?select=id_annonce,commentaire,commentaire_zones&{filtre}offset={offset}&limit=1000",
            headers=sh,
            timeout=30,
        )
        if r.status_code != 200 and tracking:
            print("colonne commentaires_enrichis_at absente -> mode --all", flush=True)
            tracking = False
            filtre = ""
            offset = 0
            rows = []
            continue
        batch = r.json()
        rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    print(f"{len(rows)} recherche(s) à enrichir ({'toutes' if not tracking else 'nouvelles uniquement'})", flush=True)

    def fetch(pid):
        base = pid[:20]
        # L'API bride vite (429) : retry avec backoff, sinon on perd des commentaires
        for attempt in range(MAX_RETRIES):
            try:
                r = requests.post(
                    DETAILS_URL,
                    headers=ah,
                    json={"prospection_id": base, "prospection_map_id": pid},
                    timeout=30,
                )
            except requests.RequestException:
                time.sleep(3 * (attempt + 1))
                continue
            if r.status_code == 429:
                time.sleep(3 * (attempt + 1))
                continue
            return pid, r, True
        return pid, None, False

    def patch(pid, comment, loc_comment, stamp):
        payload = {"commentaire": comment, "commentaire_zones": loc_comment}
        if stamp:
            payload["commentaires_enrichis_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        r = requests.patch(
            f"{supa}/rest/v1/profoods_demandes_clients?id_annonce=eq.{pid}",
            headers={**sh, "Content-Type": "application/json", "Prefer": "return=minimal"},
            json=payload,
            timeout=30,
        )
        return r.status_code in (200, 204)

    updated = errors = api_failures = 0
    # Traitement séquentiel cadencé + PATCH immédiat : l'API bride fortement
    # dès qu'on parallélise, et les mises à jour restent visibles en cours de route.
    for i, row in enumerate(rows):
        pid = row["id_annonce"]
        pid, resp, ok = fetch(pid)
        if not ok or resp is None or resp.status_code != 200:
            api_failures += 1
        else:
            d = resp.json()
            comment = (d.get("comment") or "").strip() or None
            loc_comment = (d.get("locations_comment") or "").strip() or None
            content_changed = (comment is not None or loc_comment is not None) and (
                comment != (row.get("commentaire") or None)
                or loc_comment != (row.get("commentaire_zones") or None)
            )
            # En mode suivi on PATCH même sans commentaire : le timestamp évite
            # de re-solliciter l'API chaque jour pour une recherche sans contenu.
            if content_changed or tracking:
                if patch(pid, comment, loc_comment, stamp=tracking):
                    if content_changed:
                        updated += 1
                else:
                    errors += 1
        time.sleep(0.4)
        if (i + 1) % 50 == 0:
            print(f"{i + 1}/{len(rows)} updated={updated} api_failures={api_failures}", flush=True)

    print(f"demandes={len(rows)} updated={updated} errors={errors} api_failures={api_failures}")


if __name__ == "__main__":
    main()
