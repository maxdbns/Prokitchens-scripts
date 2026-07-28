"""
Enrichissement Google Places en masse — leads 56.10C + 56.21Z
Priorité par score décroissant.
"""

import requests
import time
from datetime import datetime

GOOGLE_API_KEY = "AIzaSyA9mLoqkEtojwJEC4jAze1jdafcKw2qH6Y"
SUPABASE_URL = "https://hxjryfaakdpwfgseirik.supabase.co"
SUPABASE_API_KEY = "sb_publishable_a7xpn8srwByQrW1rXwpdlw_eQnwAoHT"

BATCH_SIZE = 200
MAX_LEADS = 10000
REQUEST_DELAY = 0.25
LOG_FILE = "/zpool/one/maxime.debaugnies/logs/google_enrich_mass.log"

headers_read = {
    "apikey": SUPABASE_API_KEY,
    "Authorization": f"Bearer {SUPABASE_API_KEY}",
    "Accept": "application/json",
    "Prefer": "count=exact",
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


def fetch_unenriched(offset, limit):
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/leads",
        params={
            "select": "siren,nom,ville,score",
            "enriched_google": "eq.false",
            "code_naf": "in.(56.10C,56.21Z)",
            "order": "score.desc",
            "offset": offset,
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
    log("=" * 60)
    log("Démarrage enrichissement Google Places — 56.10C + 56.21Z")
    log("=" * 60)

    total = 0
    found_phone = 0
    found_website = 0
    offset = 0

    while total < MAX_LEADS:
        batch = fetch_unenriched(offset, BATCH_SIZE)
        if not batch:
            log("Plus aucun lead à enrichir !")
            break

        log(f"Batch de {len(batch)} leads (offset={offset})")

        for lead in batch:
            if total >= MAX_LEADS:
                break

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
            total += 1

            if phone or website:
                log(f"  [{total}] {nom[:40]:40s} | tel={phone or '-':20s} | web={'oui' if website else '-'}")

            if total % 100 == 0:
                log(f"── {total}/{MAX_LEADS} traités | {found_phone} tél | {found_website} web ──")

            time.sleep(REQUEST_DELAY)

        offset += len(batch)

    log("=" * 60)
    log(f"TERMINÉ: {total} traités, {found_phone} téléphones, {found_website} sites web")
    log("=" * 60)


if __name__ == "__main__":
    main()
