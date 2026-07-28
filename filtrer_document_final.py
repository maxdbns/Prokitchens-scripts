"""
Genere le document final de leads ProKitchens.
Criteres :
  - Hors book of business Salesforce
  - NAF cible (56.10C / 56.21Z)
  - Activite confirmee restauration par Google Places
  - Contact verifie (telephone ou site web)
  - Croissance de CA positive sur les 2 derniers exercices connus (INPI)
  - Au moins 3 sites (chaîne / multi-sites)
"""

import csv
import re

INPUT_CSV = "data/leads_final_croissance.csv"
OUTPUT_CSV = "data/LEADS_PROKITCHES_FINAL.csv"

POSITIVE_TYPES = {
    "restaurant", "meal_delivery", "meal_takeaway", "cafe", "bakery", "food"
}
NEGATIVE_TYPES = {
    "health", "hospital", "bank", "finance", "real_estate_agency",
    "jewelry_store", "tourist_attraction", "general_contractor", "painter",
    "supermarket", "gas_station", "car_dealer", "lawyer", "insurance_agency",
    "clothing_store", "dentist", "subway_station", "train_station", "transit_station"
}


def est_restaurant(types_str):
    if not types_str:
        return False
    types = {t.strip().lower() for t in str(types_str).split(",") if t.strip()}
    if types & NEGATIVE_TYPES:
        return False
    return bool(types & POSITIVE_TYPES)


def telephone_valide(phone):
    if not phone:
        return False
    return len(re.sub(r"\D", "", str(phone))) >= 8


def site_valide(url):
    if not url:
        return False
    url = str(url).strip().lower()
    return url not in ("nan", "n/a", "-", "none", "") and (
        url.startswith("http://") or url.startswith("https://")
    )


def main():
    with open(INPUT_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        leads = list(reader)

    final = []
    for lead in leads:
        # Activite restaurant
        if not est_restaurant(lead.get("google_types", "")):
            continue

        # Contact verifie
        if not (telephone_valide(lead.get("Telephone", "")) or site_valide(lead.get("Site Web", ""))):
            continue

        # Au moins 3 sites
        try:
            nb_sites = int(float(lead.get("Nb Sites", "0") or "0"))
        except ValueError:
            nb_sites = 0
        if nb_sites < 3:
            continue

        # Croissance CA positive
        pct_str = lead.get("ca_croissance_pct", "").strip()
        if not pct_str:
            continue
        try:
            pct = float(pct_str)
        except ValueError:
            continue
        if pct <= 0:
            continue

        final.append(lead)

    # Tri : croissance decroissante, puis score, puis CA
    final.sort(
        key=lambda x: (
            float(x.get("ca_croissance_pct", "0") or "0"),
            int(float(x.get("Score", "0") or "0")),
            int(float(x.get("CA", "0") or "0"))
        ),
        reverse=True,
    )

    # Colonnes selectionnees pour le document final
    selected_cols = [
        "Nom", "SIREN", "Ville", "Code Postal", "NAF",
        "Telephone", "Site Web", "Dirigeant",
        "CA", "Nb Sites", "ca_croissance_pct", "Score",
    ]

    with open(OUTPUT_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=selected_cols, extrasaction="ignore")
        writer.writeheader()
        for lead in final:
            row = {col: lead.get(col, "") for col in selected_cols}
            writer.writerow(row)

    print(f"Leads finaux ProKitchens : {len(final)}")
    print(f"Fichier : {OUTPUT_CSV}")
    print("\nTop leads :")
    for lead in final[:10]:
        print(
            f"  {lead.get('Nom','?')[:35]:<35} | CA {lead.get('CA','?'):>12} | "
            f"Sites {lead.get('Nb Sites','?'):>3} | Croissance {lead.get('ca_croissance_pct','?'):>6}% | "
            f"Tel {lead.get('Telephone','')[:18]:<18}"
        )


if __name__ == "__main__":
    main()
