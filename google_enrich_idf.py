"""
Enrichissement Google Places — QSR (56.10C) Île-de-France uniquement.
Priorité par score décroissant. Pas de limite de leads.
"""

import requests
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

GOOGLE_API_KEY = "AIzaSyA9mLoqkEtojwJEC4jAze1jdafcKw2qH6Y"
SUPABASE_URL = "https://hxjryfaakdpwfgseirik.supabase.co"
SUPABASE_API_KEY = "sb_publishable_a7xpn8srwByQrW1rXwpdlw_eQnwAoHT"

BATCH_SIZE = 500
WORKERS = 8
LOG_FILE = "/zpool/one/maxime.debaugnies/logs/google_enrich_idf.log"

IDF_FILTER = "or=(code_postal.like.75*,code_postal.like.77*,code_postal.like.78*,code_postal.like.91*,code_postal.like.92*,code_postal.like.93*,code_postal.like.94*,code_postal.like.95*)"

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

stats = {"total": 0, "phone": 0, "website": 0}


def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def fetch_unenriched(limit):
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/leads?{IDF_FILTER}",
        params={
            "select": "siren,nom,ville,score",
            "enriched_google": "eq.false",
            "code_naf": "eq.56.10C",
            "order": "score.desc.nullslast",
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
        return None, None


def process_lead(lead):
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
    if website:
        update["site_web"] = website

    try:
        requests.patch(
            f"{SUPABASE_URL}/rest/v1/leads?siren=eq.{siren}",
            headers=headers_write,
            json=update,
            timeout=15,
        )
    except Exception:
        pass

    return siren, nom, phone, website


def main():
    log("=" * 60)
    log("Enrichissement Google Places — QSR (56.10C) Île-de-France")
    log(f"Workers: {WORKERS} | Batch: {BATCH_SIZE}")
    log("=" * 60)

    while True:
        batch = fetch_unenriched(BATCH_SIZE)
        if not batch:
            log("Plus aucun lead à enrichir !")
            break

        log(f"Batch de {len(batch)} leads")

        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = {pool.submit(process_lead, lead): lead for lead in batch}
            for future in as_completed(futures):
                try:
                    siren, nom, phone, website = future.result()
                except Exception:
                    continue

                stats["total"] += 1
                if phone:
                    stats["phone"] += 1
                if website:
                    stats["website"] += 1

                if phone or website:
                    log(f"  [{stats['total']}] {nom[:40]:40s} | tel={phone or '-':20s} | web={'oui' if website else '-'}")

                if stats["total"] % 500 == 0:
                    log(f"── {stats['total']} traités | {stats['phone']} tél | {stats['website']} web ──")

    log("=" * 60)
    log(f"TERMINÉ: {stats['total']} traités, {stats['phone']} téléphones, {stats['website']} sites web")
    log("=" * 60)


if __name__ == "__main__":
    main()
