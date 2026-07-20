"""
Enrichissement INPI — Croissance CA (YoY)
Cible les leads déjà enrichis INPI qui ont un CA mais pas encore de CA précédent.
Récupère le 2e bilan le plus récent pour calculer la croissance.
"""

import requests
import time
from datetime import datetime

# ─── Config ───
import os

INPI_USERNAME = os.environ.get("INPI_USERNAME")
INPI_PASSWORD = os.environ.get("INPI_PASSWORD")
INPI_BASE_URL = "https://registre-national-entreprises.inpi.fr/api"

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://hxjryfaakdpwfgseirik.supabase.co")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY")
SUPABASE_TABLE = "leads"

DAILY_QUOTA = 9500
REQUEST_DELAY = 0.35
BATCH_SIZE = 500
LOG_FILE = "/zpool/one/maxime.debaugnies/inpi_enrich_growth.log"


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
    log("Connecte a l'API INPI")
    return resp.json()["token"]


def fetch_leads(offset, limit):
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}",
        params={
            "select": "siren,nom,chiffre_affaires,date_cloture_bilan",
            "enriched_inpi": "eq.true",
            "chiffre_affaires": "not.is.null",
            "ca_precedent": "is.null",
            "order": "score.desc.nullslast",
            "offset": offset,
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


def parse_montant(val):
    if not val:
        return None
    try:
        return int(val.strip())
    except (ValueError, TypeError):
        return None


def extract_two_bilans(bilans_saisis):
    """Extrait les CA des 2 bilans les plus récents (publics, non supprimés)."""
    results = []
    for bs in bilans_saisis:
        if bs.get("confidentiality") != "Public" or bs.get("deleted", False):
            continue

        bilan = bs.get("bilanSaisi", {}).get("bilan", {})
        identite = bilan.get("identite", {})
        date_cloture = identite.get("dateClotureExercice", "")

        ca = None
        for page in bilan.get("detail", {}).get("pages", []):
            for liasse in page.get("liasses", []):
                code = liasse.get("code", "")
                if code == "FL":
                    ca = parse_montant(liasse.get("m3") or liasse.get("m1"))
                elif code == "FJ" and ca is None:
                    ca = parse_montant(liasse.get("m3") or liasse.get("m1"))

        if ca is not None:
            results.append({"ca": ca, "date_cloture": date_cloture})

        if len(results) >= 2:
            break

    return results


def get_growth_data(siren, headers):
    try:
        resp = requests.get(
            f"{INPI_BASE_URL}/companies/{siren}/attachments",
            headers=headers,
            timeout=30,
        )
    except requests.RequestException as e:
        log(f"  Erreur reseau SIREN {siren}: {e}")
        return None

    if resp.status_code == 404:
        return None
    if resp.status_code == 429:
        log("  Rate limit atteint, pause 60s...")
        time.sleep(60)
        return get_growth_data(siren, headers)
    if resp.status_code == 401:
        return "REAUTH"
    if resp.status_code != 200:
        return None

    bilans_saisis = resp.json().get("bilansSaisis", [])
    bilans = extract_two_bilans(bilans_saisis)

    if len(bilans) < 2:
        return None

    ca_recent = bilans[0]["ca"]
    ca_ancien = bilans[1]["ca"]

    if ca_ancien == 0:
        return None

    croissance = ((ca_recent - ca_ancien) / abs(ca_ancien)) * 100

    return {
        "ca_precedent": ca_ancien,
        "date_cloture_bilan_previous": bilans[1]["date_cloture"],
        "croissance_ca": round(croissance, 2),
    }


def patch_lead(siren, growth_data):
    resp = requests.patch(
        f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}?siren=eq.{siren}",
        headers={
            "apikey": SUPABASE_API_KEY,
            "Authorization": f"Bearer {SUPABASE_API_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        json=growth_data,
        timeout=30,
    )
    return resp.status_code in (200, 204)


def main():
    if not INPI_USERNAME or not INPI_PASSWORD or not SUPABASE_API_KEY:
        log("ERREUR: variables d'environnement INPI_USERNAME, INPI_PASSWORD et SUPABASE_API_KEY requises.")
        return

    log("=" * 60)
    log("Demarrage enrichissement INPI — Croissance CA (YoY)")
    log("=" * 60)

    token = inpi_login()
    headers = {"Authorization": f"Bearer {token}"}

    total_processed = 0
    total_growth_found = 0
    total_no_second_bilan = 0
    api_calls = 0

    offset = 0
    while api_calls < DAILY_QUOTA:
        remaining = DAILY_QUOTA - api_calls
        batch_size = min(BATCH_SIZE, remaining)

        leads = fetch_leads(offset, batch_size)
        if not leads:
            log("Plus aucun lead a enrichir pour la croissance !")
            break

        log(f"Batch de {len(leads)} leads (offset={offset}, API calls: {api_calls}/{DAILY_QUOTA})")
        offset += len(leads)

        for lead in leads:
            if api_calls >= DAILY_QUOTA:
                log(f"Quota journalier atteint ({DAILY_QUOTA} requetes)")
                break

            siren = lead["siren"]
            nom = lead.get("nom", "?")[:45]
            ca_actuel = lead.get("chiffre_affaires", 0)

            growth = get_growth_data(siren, headers)
            api_calls += 1

            if growth == "REAUTH":
                log("Token expire, reconnexion...")
                token = inpi_login()
                headers = {"Authorization": f"Bearer {token}"}
                growth = get_growth_data(siren, headers)
                api_calls += 1

            if growth:
                total_growth_found += 1
                pct = growth["croissance_ca"]
                arrow = "+" if pct >= 0 else ""
                log(f"  [{total_processed+1}] {nom:45s} CA={ca_actuel:>12,} -> {arrow}{pct:.1f}%")
                patch_lead(siren, growth)
            else:
                total_no_second_bilan += 1
                patch_lead(siren, {"ca_precedent": 0, "croissance_ca": None})

            total_processed += 1
            time.sleep(REQUEST_DELAY)

    log("=" * 60)
    pct = (total_growth_found / total_processed * 100) if total_processed else 0
    log(f"TERMINE: {total_processed} traites, {total_growth_found} avec croissance ({pct:.1f}%)")
    log(f"Sans 2e bilan: {total_no_second_bilan}")
    log(f"Appels API: {api_calls}/{DAILY_QUOTA}")
    log("=" * 60)


if __name__ == "__main__":
    main()
