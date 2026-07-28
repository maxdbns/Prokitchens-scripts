"""
Croise les candidats Sirene avec les leads existants pour recuperer les contacts/scores.
"""
import csv
from check_bob import est_dans_bob, charger_book, normaliser_nom

SIRENE_CSV = "data/sirene_qsr_candidates.csv"
EXISTING_CSV = "data/leads_manquants_salesforce.csv"
FINAL_CSV = "data/leads_existing_clean.csv"
OUTPUT = "data/leads_supplementaires.csv"

# Marques a exclure explicitement
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
    "MOZZA", "BOKIT", "Poke Me", "POKE ME", "DARK KITCHEN", "FAMILEAT",
}


def is_excluded_brand(nom):
    n = normaliser_nom(nom)
    for brand in EXCLUDED_BRANDS:
        if normaliser_nom(brand) in n:
            return True
    return False


def load_existing_leads():
    by_siren = {}
    with open(EXISTING_CSV, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            siren = row.get("SIREN", "").strip().zfill(9)
            if siren:
                by_siren[siren] = row
    return by_siren


def load_existing_final_sirens():
    sirens = set()
    with open(FINAL_CSV, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            siren = row.get("SIREN", "").strip().zfill(9)
            if siren:
                sirens.add(siren)
    return sirens


def main():
    book = charger_book()
    existing_leads = load_existing_leads()
    existing_final = load_existing_final_sirens()

    with open(SIRENE_CSV, "r", encoding="utf-8") as f:
        candidates = list(csv.DictReader(f))

    supplementary = []
    for c in candidates:
        siren = c["siren"].strip().zfill(9)
        if siren in existing_final:
            continue
        if siren not in existing_leads:
            continue

        lead = existing_leads[siren]
        nom = lead.get("Nom", "")

        if is_excluded_brand(nom):
            print(f"  [EXCLU MARQUE] {nom}")
            continue

        is_bob, match = est_dans_bob(nom, book)
        if is_bob:
            print(f"  [EXCLU BOB] {nom} -> {match}")
            continue

        supplementary.append(lead)

    print(f"\n{len(supplementary)} leads supplementaires trouves dans leads_manquants_salesforce.csv")

    with open(OUTPUT, "w", encoding="utf-8", newline="") as f:
        if supplementary:
            writer = csv.DictWriter(f, fieldnames=supplementary[0].keys())
            writer.writeheader()
            writer.writerows(supplementary)

    print(f"Fichier : {OUTPUT}")


if __name__ == "__main__":
    main()
