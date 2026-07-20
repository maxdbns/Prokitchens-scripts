"""
Complete les leads finaux avec les leads qualifies enrichis par Google,
hors BOB et correspondant aux criteres de qualite.
"""
import csv
import re
from check_bob import est_dans_bob, charger_book, normaliser_nom

INPUT = "leads_qualifies_enrichis.csv"
FINAL_CSV = "leads_existing_clean.csv"
OUTPUT = "leads_final_pool.csv"

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
    "DAILYMONOP", "AMREST", "BURGER KING", "KFC", "FOODCHERI", "LENOTRE",
    "POTEL & CHABOT", "DALLOYAU", "DAILYMONOP", "MONOPRIX", "GARES SNCF",
    "BURGER KING", "KFC", "MCDONALD", "QUICK", "SUBWAY", "PIZZA HUT",
}


def is_excluded_brand(nom):
    n = normaliser_nom(nom)
    for brand in EXCLUDED_BRANDS:
        if normaliser_nom(brand) in n:
            return True
    return False


def load_existing_final_sirens():
    sirens = set()
    with open(FINAL_CSV, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            siren = row.get("SIREN", "").strip().zfill(9)
            if siren:
                sirens.add(siren)
    return sirens


def is_valid_phone(phone):
    if not phone:
        return False
    digits = re.sub(r"\D", "", phone)
    return len(digits) >= 10 and digits.startswith("3")


def has_google_food_type(row):
    types = (row.get("google_types", "") or "").lower().strip()
    # Accepte si Google n'a pas trouve de types (donnees incomplètes) ou si types alimentaires
    if not types:
        return True
    return any(t in types for t in ["restaurant", "food", "meal_delivery", "cafe", "bakery"])


def main():
    book = charger_book()
    existing_final = load_existing_final_sirens()

    with open(INPUT, "r", encoding="utf-8") as f:
        leads = list(csv.DictReader(f))

    selected = []
    for lead in leads:
        siren = lead.get("SIREN", "").strip().zfill(9)
        if siren in existing_final:
            continue

        nom = lead.get("Nom", "").strip()
        naf = lead.get("NAF", "").strip()
        try:
            score = int(float(lead.get("Score", "0") or "0"))
        except ValueError:
            score = 0
        try:
            nb_sites = int(float(lead.get("Nb Sites", "0") or "0"))
        except ValueError:
            nb_sites = 0

        phone = lead.get("Telephone", "").strip() or lead.get("google_phone", "").strip()
        website = lead.get("Site Web", "").strip() or lead.get("google_website", "").strip()
        contact_fiable = lead.get("contact_fiable", "").strip()

        if naf not in ("56.10C", "56.21Z"):
            continue
        if score < 50:
            continue
        if nb_sites < 3:
            continue
        if not (is_valid_phone(phone) or website):
            continue
        if not has_google_food_type(lead):
            continue
        if is_excluded_brand(nom):
            continue

        is_bob, match = est_dans_bob(nom, book)
        if is_bob:
            print(f"  [BOB] {nom} -> {match}")
            continue

        selected.append(lead)

    print(f"\n{len(selected)} leads selectionnes depuis {INPUT}")

    with open(OUTPUT, "w", encoding="utf-8", newline="") as f:
        if selected:
            writer = csv.DictWriter(f, fieldnames=selected[0].keys())
            writer.writeheader()
            writer.writerows(selected)

    print(f"Fichier : {OUTPUT}")


if __name__ == "__main__":
    main()
