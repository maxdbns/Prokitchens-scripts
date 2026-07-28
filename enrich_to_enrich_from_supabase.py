"""
Enrichit les leads to_enrich depuis Supabase.
Lit LEADS_PROKITCHES_TO_ENRICH.csv, recupere les contacts stockes dans la table leads,
et ecrit LEADS_PROKITCHES_TO_ENRICH_ENRICHIS.csv.
"""

import csv
import os
import requests

SUPABASE_URL = "https://hxjryfaakdpwfgseirik.supabase.co"
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY")
if not SUPABASE_API_KEY:
    raise RuntimeError("Variable d'environnement SUPABASE_API_KEY requise")

INPUT_CSV = "data/LEADS_PROKITCHES_TO_ENRICH.csv"
OUTPUT_CSV = "data/LEADS_PROKITCHES_TO_ENRICH_ENRICHIS.csv"

HEADERS = {
    "apikey": SUPABASE_API_KEY,
    "Authorization": f"Bearer {SUPABASE_API_KEY}",
    "Content-Type": "application/json",
}


def fetch_lead(siren):
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/leads",
            params={"siren": f"eq.{siren}", "select": "siren,telephone,site_web,nom"},
            headers=HEADERS,
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        if data:
            return data[0]
        return None
    except Exception as e:
        print(f"  Erreur Supabase for {siren}: {e}")
        return None


def main():
    with open(INPUT_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        leads = list(reader)
        fieldnames = reader.fieldnames

    extra_cols = ["supabase_phone", "supabase_website", "contact_fiable"]
    for col in extra_cols:
        if col not in fieldnames:
            fieldnames.append(col)

    total = len(leads)
    corrected = 0

    for i, lead in enumerate(leads, 1):
        siren = lead.get("SIREN", "").strip().zfill(9)
        nom = lead.get("Nom", "?")
        print(f"[{i}/{total}] {nom}")

        data = fetch_lead(siren)
        phone = ""
        website = ""
        if data:
            phone = data.get("google_phone") or data.get("telephone") or ""
            website = data.get("google_website") or data.get("site_web") or ""

        lead["supabase_phone"] = phone
        lead["supabase_website"] = website
        lead["contact_fiable"] = "oui" if (phone or website) else "non"

        if phone:
            lead["Telephone"] = phone
        if website:
            lead["Site Web"] = website

        if phone or website:
            corrected += 1
            print(f"  -> tel={phone or '-'} | web={website or '-'}")

    with open(OUTPUT_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(leads)

    print(f"\nTERMINE: {total} leads, {corrected} contacts enrichis")
    print(f"Sortie: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
