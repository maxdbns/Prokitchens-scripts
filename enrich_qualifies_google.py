"""
Enrichissement Google Places des leads qualifies.
Lit leads_qualifies.csv, recherche chaque lead sur Google Places,
et ecrit leads_qualifies_enrichis.csv avec telephones/sites corriges.
"""

import csv
import time
from datetime import datetime
import requests

GOOGLE_API_KEY = "AIzaSyA9mLoqkEtojwJEC4jAze1jdafcKw2qH6Y"
INPUT_CSV = "leads_qualifies.csv"
OUTPUT_CSV = "leads_qualifies_enrichis.csv"
LOG_FILE = "enrich_qualifies_google.log"
REQUEST_DELAY = 0.3


def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def google_enrich(name, city):
    try:
        search_resp = requests.get(
            "https://maps.googleapis.com/maps/api/place/textsearch/json",
            params={"query": f"{name} {city}", "key": GOOGLE_API_KEY, "language": "fr"},
            timeout=15,
        )
        if search_resp.status_code != 200:
            return None, None, []

        results = search_resp.json().get("results", [])
        if not results:
            return None, None, []

        place_id = results[0]["place_id"]

        details_resp = requests.get(
            "https://maps.googleapis.com/maps/api/place/details/json",
            params={
                "place_id": place_id,
                "fields": "international_phone_number,website,formatted_address,types",
                "key": GOOGLE_API_KEY,
                "language": "fr",
            },
            timeout=15,
        )
        if details_resp.status_code != 200:
            return None, None, []

        result = details_resp.json().get("result", {})
        return (
            result.get("international_phone_number"),
            result.get("website"),
            result.get("types", []),
        )
    except Exception as e:
        log(f"  Erreur Google for {name}: {e}")
        return None, None, []


def main():
    log("=" * 60)
    log("Enrichissement Google Places — leads qualifies")
    log("=" * 60)

    with open(INPUT_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        leads = list(reader)
        fieldnames = reader.fieldnames

    # Ajoute des colonnes pour les donnees corrigees
    extra_cols = ["google_phone", "google_website", "google_types", "contact_fiable"]
    for col in extra_cols:
        if col not in fieldnames:
            fieldnames.append(col)

    total = len(leads)
    corrected = 0

    for i, lead in enumerate(leads, 1):
        nom = lead.get("Nom", "?")
        ville = lead.get("Ville", "")
        log(f"[{i}/{total}] {nom[:40]} ({ville})")

        phone, website, types = google_enrich(nom, ville)

        lead["google_phone"] = phone or ""
        lead["google_website"] = website or ""
        lead["google_types"] = ",".join(types) if types else ""

        # On considere le contact fiable si on a trouve un telephone ou un site web chez Google
        lead["contact_fiable"] = "oui" if (phone or website) else "non"

        if phone:
            lead["Telephone"] = phone
        if website:
            lead["Site Web"] = website

        if phone or website:
            corrected += 1
            log(f"  -> tel={phone or '-'} | web={website or '-'} | types={lead['google_types']}")

        time.sleep(REQUEST_DELAY)

    with open(OUTPUT_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(leads)

    log("=" * 60)
    log(f"TERMINE: {total} leads, {corrected} contacts corriges")
    log(f"Sortie: {OUTPUT_CSV}")
    log("=" * 60)


if __name__ == "__main__":
    main()
