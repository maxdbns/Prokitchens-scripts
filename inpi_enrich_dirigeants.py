"""
Enrichissement dirigeants — QSR Paris (NAF 56.10C, 75xxx)
Cible les leads déjà enrichis INPI (financier) mais sans dirigeant.
À lancer après la fin de l'enrichissement financier.
"""

import requests
import time
from datetime import datetime

# ─── Config ───
INPI_USERNAME = "maxime.debaugnies@cloudkitchens.com"
INPI_PASSWORD = "Thomas36130!"
INPI_BASE_URL = "https://registre-national-entreprises.inpi.fr/api"

SUPABASE_URL = "https://hxjryfaakdpwfgseirik.supabase.co"
SUPABASE_API_KEY = "sb_publishable_a7xpn8srwByQrW1rXwpdlw_eQnwAoHT"
SUPABASE_TABLE = "leads"

DAILY_QUOTA = 9500
REQUEST_DELAY = 0.35
BATCH_SIZE = 1000
LOG_FILE = "/zpool/one/maxime.debaugnies/inpi_enrich_dirigeants.log"

ROLE_LABELS = {
    "53": "Président",
    "65": "Directeur général",
    "10": "Gérant",
    "11": "Co-gérant",
    "16": "Président du conseil d'administration",
    "17": "Administrateur",
}


def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def inpi_login():
    resp = requests.post(
        f"{INPI_BASE_URL}/sso/login",
        json={"username": INPI_USERNAME, "password": INPI_PASSWORD},
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    log("Connecté à l'API INPI")
    return resp.json()["token"]


def fetch_leads(limit):
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}",
        params={
            "select": "siren,nom,ville",
            "code_naf": "eq.56.10C",
            "code_postal": "like.75*",
            "enriched_inpi": "eq.true",
            "dirigeant_nom": "is.null",
            "limit": limit,
        },
        headers={
            "apikey": SUPABASE_API_KEY,
            "Authorization": f"Bearer {SUPABASE_API_KEY}",
            "Accept": "application/json",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def extract_dirigeant(data):
    pouvoirs = (
        data.get("formality", {})
        .get("content", {})
        .get("personneMorale", {})
        .get("composition", {})
        .get("pouvoirs", [])
    )

    for pouvoir in pouvoirs:
        individu = pouvoir.get("individu", {})
        desc = individu.get("descriptionPersonne", {})
        nom = desc.get("nom")
        prenoms = desc.get("prenoms", [])
        role_code = pouvoir.get("roleEntreprise", "")

        if nom and prenoms:
            return {
                "dirigeant_nom": nom.title(),
                "dirigeant_prenom": prenoms[0].title(),
                "dirigeant_role": ROLE_LABELS.get(role_code, role_code),
            }

    return None


def get_dirigeant(siren, headers):
    try:
        resp = requests.get(
            f"{INPI_BASE_URL}/companies/{siren}",
            headers=headers,
            timeout=30,
        )
    except requests.RequestException as e:
        log(f"  Erreur réseau SIREN {siren}: {e}")
        return None

    if resp.status_code == 404:
        return None
    if resp.status_code == 429:
        log("  Rate limit, pause 60s...")
        time.sleep(60)
        return get_dirigeant(siren, headers)
    if resp.status_code == 401:
        return "REAUTH"
    if resp.status_code != 200:
        return None

    return extract_dirigeant(resp.json())


def patch_lead(siren, dirigeant_data):
    resp = requests.patch(
        f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}?siren=eq.{siren}",
        headers={
            "apikey": SUPABASE_API_KEY,
            "Authorization": f"Bearer {SUPABASE_API_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        json=dirigeant_data,
        timeout=30,
    )
    return resp.status_code in (200, 204)


def main():
    log("=" * 60)
    log("Démarrage enrichissement dirigeants — QSR Paris")
    log("=" * 60)

    token = inpi_login()
    headers = {"Authorization": f"Bearer {token}"}

    total_processed = 0
    total_found = 0
    api_calls = 0

    while api_calls < DAILY_QUOTA:
        remaining = DAILY_QUOTA - api_calls
        batch_size = min(BATCH_SIZE, remaining)

        leads = fetch_leads(batch_size)
        if not leads:
            log("Plus aucun lead à enrichir !")
            break

        log(f"Batch de {len(leads)} leads (API calls: {api_calls}/{DAILY_QUOTA})")

        for lead in leads:
            if api_calls >= DAILY_QUOTA:
                log(f"Quota journalier atteint ({DAILY_QUOTA})")
                break

            siren = lead["siren"]
            nom = lead.get("nom", "?")[:45]

            dirigeant = get_dirigeant(siren, headers)
            api_calls += 1

            if dirigeant == "REAUTH":
                log("Token expiré, reconnexion...")
                token = inpi_login()
                headers = {"Authorization": f"Bearer {token}"}
                dirigeant = get_dirigeant(siren, headers)
                api_calls += 1

            if dirigeant:
                total_found += 1
                role = dirigeant.pop("dirigeant_role", "")
                log(f"  [{total_processed+1}] {nom:45s} -> {dirigeant['dirigeant_prenom']} {dirigeant['dirigeant_nom']} ({role})")
                patch_lead(siren, dirigeant)
            else:
                patch_lead(siren, {"dirigeant_nom": ""})

            total_processed += 1

            if total_processed % 500 == 0:
                pct = (total_found / total_processed * 100) if total_processed else 0
                log(f"── Progression: {total_processed} traités, {total_found} dirigeants ({pct:.1f}%), {api_calls} appels API ──")

            time.sleep(REQUEST_DELAY)

    log("=" * 60)
    pct = (total_found / total_processed * 100) if total_processed else 0
    log(f"TERMINÉ: {total_processed} traités, {total_found} dirigeants trouvés ({pct:.1f}%)")
    log(f"Appels API: {api_calls}/{DAILY_QUOTA}")
    log("=" * 60)


if __name__ == "__main__":
    main()
