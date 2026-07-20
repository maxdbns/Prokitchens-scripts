"""
Filtre final des leads qualifies enrichis.
Garder uniquement ceux dont Google Places confirme une activite de restauration.
"""

import csv

INPUT_CSV = "leads_qualifies_enrichis.csv"
OUTPUT_CSV = "leads_final.csv"

# Types Google Places qui qualifient une activite de restauration
POSITIVE_TYPES = {
    "restaurant", "meal_delivery", "meal_takeaway", "cafe", "bakery", "food"
}

# Types qui disqualifient clairement (hopitaux, banques, agences, etc.)
NEGATIVE_TYPES = {
    "health", "hospital", "bank", "finance", "real_estate_agency",
    "jewelry_store", "tourist_attraction", "general_contractor", "painter",
    "supermarket", "gas_station", "car_dealer", "lawyer", "insurance_agency"
}


def est_restaurant(types_str):
    if not types_str:
        return False
    types = {t.strip().lower() for t in str(types_str).split(",") if t.strip()}
    if types & NEGATIVE_TYPES:
        return False
    return bool(types & POSITIVE_TYPES)


def main():
    with open(INPUT_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        leads = list(reader)
        fieldnames = reader.fieldnames

    gardes = []
    for lead in leads:
        types = lead.get("google_types", "")
        if not est_restaurant(types):
            continue
        if lead.get("contact_fiable") != "oui":
            continue
        gardes.append(lead)

    # Tri par score decroissant
    gardes.sort(key=lambda x: int(float(x.get("Score", "0") or "0")), reverse=True)

    with open(OUTPUT_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(gardes)

    print(f"Leads finaux : {len(gardes)}")
    print(f"Fichier : {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
