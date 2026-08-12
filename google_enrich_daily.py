"""
Enrichissement Google Places quotidien — tous codes NAF ProKitchens.

Tourne dans GitHub Actions. Chaque run traite BATCH_SIZE leads
parmi ceux avec enriched_google=false, triés par score décroissant.

2 appels API Google par lead (Text Search + Place Details).
"""

import os
import sys
import time
import requests
from datetime import datetime

import prokitchens_env
prokitchens_env.load_env()

GOOGLE_API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY", "")
SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_API_KEY = os.environ["SUPABASE_API_KEY"]

BATCH_SIZE = int(os.environ.get("GOOGLE_ENRICH_BATCH", "500"))
REQUEST_DELAY = 0.25
NAF_CODES = '("56.10C","56.21Z","56.29B")'

os.makedirs("logs", exist_ok=True)
LOG_FILE = os.path.join("logs", "google_enrich_daily.log")

headers_read = {
    "apikey": SUPABASE_API_KEY,
    "Authorization": f"Bearer {SUPABASE_API_KEY}",
    "Accept": "application/json",
}
headers_write = {
    "apikey": SUPABASE_API_KEY,
    "Authorization": f"Bearer {SUPABASE_API_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}


def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def fetch_unenriched(limit):
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/leads",
        params={
            "select": "siren,nom,ville,score_total",
            "enriched_google": "eq.false",
            "code_naf": f"in.{NAF_CODES}",
            "statut": "neq.ferme",
            "order": "score_total.desc.nullslast",
            "limit": limit,
        },
        headers=headers_read,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def google_enrich(name, city):
    try:
        search_resp = requests.get(
            "https://maps.googleapis.com/maps/api/place/textsearch/json",
            params={"query": f"{name} {city}", "key": GOOGLE_API_KEY, "language": "fr"},
            timeout=15,
        )
        if search_resp.status_code != 200:
            return None, None

        results = search_resp.json().get("results", [])
        if not results:
            return None, None

        place_id = results[0]["place_id"]
        time.sleep(REQUEST_DELAY)

        details_resp = requests.get(
            "https://maps.googleapis.com/maps/api/place/details/json",
            params={
                "place_id": place_id,
                "fields": "international_phone_number,website",
                "key": GOOGLE_API_KEY,
                "language": "fr",
            },
            timeout=15,
        )
        if details_resp.status_code != 200:
            return None, None

        result = details_resp.json().get("result", {})
        return result.get("international_phone_number"), result.get("website")
    except Exception as e:
        log(f"  Erreur Google: {e}")
        return None, None


def patch_lead(siren, data):
    try:
        resp = requests.patch(
            f"{SUPABASE_URL}/rest/v1/leads?siren=eq.{siren}",
            headers=headers_write,
            json=data,
            timeout=15,
        )
        return resp.status_code in (200, 204)
    except Exception:
        return False


def main():
    if not GOOGLE_API_KEY:
        log("ERREUR: GOOGLE_PLACES_API_KEY non définie")
        sys.exit(1)

    log("=" * 60)
    log(f"Google Places enrich — batch {BATCH_SIZE} leads")
    log("=" * 60)

    leads = fetch_unenriched(BATCH_SIZE)
    log(f"{len(leads)} leads à enrichir")

    if not leads:
        log("Rien à faire.")
        return

    found_phone = 0
    found_website = 0

    for i, lead in enumerate(leads, 1):
        siren = lead["siren"]
        nom = lead.get("nom", "?")
        ville = lead.get("ville", "")

        phone, website = google_enrich(nom, ville)

        update = {
            "enriched_google": True,
            "enriched_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        if phone:
            update["telephone"] = phone
            found_phone += 1
        if website:
            update["site_web"] = website
            found_website += 1

        patch_lead(siren, update)

        if phone or website:
            log(f"  [{i}/{len(leads)}] {nom[:40]} | tel={phone or '-'} | web={'oui' if website else '-'}")

        if i % 50 == 0:
            log(f"── {i}/{len(leads)} | {found_phone} tel | {found_website} web ──")

        time.sleep(REQUEST_DELAY)

    log("=" * 60)
    log(f"TERMINÉ: {len(leads)} traités, {found_phone} tel, {found_website} web")
    log("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"ERREUR FATALE: {e}")
        sys.exit(1)
