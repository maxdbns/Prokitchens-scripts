"""
Complete LEADS_PROKITCHES_MANUAL_REVIEW.csv avec les meilleurs leads
enrichis (contact fiable, score >= 60, 3+ sites) hors BOB et marques.
"""
import csv
import re
from check_bob import est_dans_bob, charger_book, normaliser_nom

INPUT = "data/leads_qualifies_enrichis.csv"
MANUAL_CSV = "data/LEADS_PROKITCHES_MANUAL_REVIEW.csv"
STRICT_CSV = "data/LEADS_PROKITCHES_FINAL_STRICT.csv"
OUTPUT = "data/LEADS_PROKITCHES_MANUAL_REVIEW.csv"

EXCLUDED_BRANDS = {
    "MC DONALD", "MCDONALD", "BURGER KING", "KFC", "SUBWAY", "QUICK",
    "PIZZA HUT", "DOMINO'S", "DOMINOS", "TACO BELL", "WENDY'S", "CHIPOTLE",
    "FIVE GUYS", "SHAKE SHACK", "O'TACOS", "O TACOS", "PRET A MANGER",
    "PRETAMANGER", "PAUL", "LA BRIOCHE DOREE", "BRIOCHE DOREE", "POMME DE PAIN",
    "MEZZO DI PASTA", "VAPIANO", "PLANET SUSHI", "EAT SUSHI", "SUSHI SHOP",
    "BAGELSTEIN", "BAGEL CORNER", "BIG FERNAND", "BIOBURGER", "COJEAN", "EXKI",
    "MEMPHIS COFFEE", "L'ARTISAN DU BURGER", "BURGER & FRIES", "FRESH BURRITOS",
    "HECTOR CHICKEN", "PEPE CHICKEN", "MASTER POULET", "POULET BRAISE",
    "CHICKEN STREET", "ORIGINAL CHICKEN", "TASTY CHICKEN", "TASTY CROUSTY",
    "PASTA PIZZA", "PITAYA", "POKAWA", "TACOS AVENUE", "TACOS KING", "TORTILLA",
    "CHIPOTLE", "KIMCHI", "DIM SUM", "BAO BAO", "WOK TO WALK", "RAMEN", "SUSHI BAR",
    "STARBUCKS", "JOE & THE JUICE", "SSP", "AUTOGRILL", "FRICHTI", "DUMBO",
    "COLUMBUS CAFE", "WAFFLE FACTORY", "ALICE PIZZA", "ALOHA POKE", "KIOSQUE PIZZA",
    "MOZZA", "BOKIT", "POKE ME", "DARK KITCHEN", "FAMILEAT", "MONOPRIX",
    "DAILYMONOP", "AMREST", "FOODCHERI", "LENOTRE", "POTEL & CHABOT", "DALLOYAU",
    "GARES SNCF", "SNCF", "AUCHAN", "CARREFOUR", "CASINO", "FRANPRIX", "LECLERC",
    "LIDL", "ALDI", "INTERMARCHE", "BK", "BKR", "POKE HOUSE", "COME",
    "CONCESSIONS GARES", "CONCESSIONS AEROPORTS", "PRET", "DAILY MONOP",
    "LA CROISSANTERIE", "CROISSANCE 5", "LAV'CAR", "LAV'LINGE", "INVESTISSEMENTS",
    "AGENCE TECHNOLOGIQUE", "COMMUNICATIONS", "DEVELOPPEMENT SAS", "CAFE DE FRANCE",
    "BOULANGERIES BG", "R.A.F", "R A F", "ALAIN JANIAUD", "SALIM BENYOUNES",
    "JOSUE LANOIX", "RIEM BECKER", "REX SUBS", "SOCIETE DES MAGASINS LOUIS",
    "AGTM GARES", "AGTM GARE",
}

EXCLUDED_SIRENS = {
    "378390033", "311976419", "452421332", "813725868", "801761800", "702045519",
    "478455793", "968109223", "832803639", "815183132", "339738601", "753479229",
    "823860770", "842506479", "452477656", "932455041", "834217853", "502941123",
    "531354983", "821483401", "820871085", "850864273",
}


def is_excluded_brand(nom):
    n = normaliser_nom(nom)
    for brand in EXCLUDED_BRANDS:
        if normaliser_nom(brand) in n:
            return True
    return False


def is_valid_phone(phone):
    if not phone:
        return False
    digits = re.sub(r"\D", "", phone)
    return len(digits) >= 10 and digits.startswith("3")


def load_existing_sirens():
    sirens = set()
    for path in [STRICT_CSV, MANUAL_CSV]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    s = (row.get("SIREN") or "").strip().zfill(9)
                    if s:
                        sirens.add(s)
        except FileNotFoundError:
            continue
    return sirens


def normalize_row(row):
    return {
        "Nom": row.get("Nom", ""),
        "SIREN": row.get("SIREN", "").strip().zfill(9),
        "Ville": row.get("Ville", ""),
        "Code Postal": row.get("Code Postal", ""),
        "NAF": row.get("NAF", ""),
        "Telephone": row.get("Telephone", "").strip() or row.get("google_phone", "").strip(),
        "Site Web": row.get("Site Web", "").strip() or row.get("google_website", "").strip(),
        "Dirigeant": row.get("Dirigeant", ""),
        "CA": row.get("CA", ""),
        "Nb Sites": row.get("Nb Sites", ""),
        "ca_croissance_pct": row.get("ca_croissance_pct", ""),
        "Score": row.get("Score", ""),
        "source": "enrichi_plus",
    }


def main():
    book = charger_book()
    existing_sirens = load_existing_sirens()

    with open(INPUT, "r", encoding="utf-8") as f:
        leads = list(csv.DictReader(f))

    added = []
    for lead in leads:
        siren = lead.get("SIREN", "").strip().zfill(9)
        if not siren or siren in existing_sirens:
            continue
        if siren in EXCLUDED_SIRENS:
            continue

        nom = lead.get("Nom", "").strip()
        if is_excluded_brand(nom):
            continue

        naf = lead.get("NAF", "").strip()
        if naf not in ("56.10C", "56.21Z"):
            continue

        try:
            score = int(float(lead.get("Score", "0") or "0"))
        except ValueError:
            continue
        if score < 60:
            continue

        try:
            nb_sites = int(float(lead.get("Nb Sites", "0") or "0"))
        except ValueError:
            continue
        if nb_sites < 3:
            continue

        contact_fiable = lead.get("contact_fiable", "").strip().lower()
        if contact_fiable != "oui":
            continue

        phone = lead.get("Telephone", "").strip() or lead.get("google_phone", "").strip()
        website = lead.get("Site Web", "").strip() or lead.get("google_website", "").strip()
        if not (is_valid_phone(phone) or website):
            continue

        if est_dans_bob(nom, book)[0]:
            print(f"  [BOB] {nom}")
            continue

        added.append(normalize_row(lead))

    print(f"{len(added)} leads supplementaires a ajouter")
    for a in added:
        print(f"  + {a['Nom']} (score {a['Score']}, {a['Nb Sites']} sites)")

    # Lire manual existant
    with open(MANUAL_CSV, "r", encoding="utf-8") as f:
        manual_rows = list(csv.DictReader(f))

    manual_rows.extend(added)

    # Trier par score decroissant
    manual_rows.sort(key=lambda x: int(float(x.get("Score", "0") or "0")), reverse=True)

    with open(OUTPUT, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=manual_rows[0].keys() if manual_rows else [])
        writer.writeheader()
        writer.writerows(manual_rows)

    print(f"\nManual review total : {len(manual_rows)}")


if __name__ == "__main__":
    main()
