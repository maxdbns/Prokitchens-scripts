"""
Filtre les leads supplementaires pour ne garder que les leads tres qualitatifs.
"""
import csv
import re
from check_bob import est_dans_bob, charger_book, normaliser_nom

INPUT = "data/leads_supplementaires.csv"
OUTPUT = "data/leads_supplementaires_filtered.csv"

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
}


def is_excluded_brand(nom):
    n = normaliser_nom(nom)
    for brand in EXCLUDED_BRANDS:
        if normaliser_nom(brand) in n:
            return True
    return False


def is_person_name(nom):
    """Heuristique simple : si le nom est juste prenom + nom de famille (2 mots simples)."""
    n = normaliser_nom(nom)
    words = n.split()
    if len(words) == 2 and all(len(w) > 2 for w in words):
        # Probablement un nom de personne si pas de terme commercial
        commercial_terms = {"SAS", "SARL", "SASU", "EURL", "GROUPE", "RESTAURATION", "RESTAURANT", "TRAITEUR", "FOOD", "CAFE", "COFFEE", "SNACK", "BISTROT", "BOULANGERIE", "PATISSERIE", "SANDWICH", "PIZZA", "BURGER", "TACOS", "SUSHI", "POKE", "BOWL", "KITCHEN", "DELI", "FAST", "GOOD", "FRESH", "MARKET", "SHOP", "BAR", "HOUSE", "LAB"}
        if not any(w in commercial_terms for w in words):
            return True
    return False


def is_valid_phone(phone):
    if not phone:
        return False
    digits = re.sub(r"\D", "", phone)
    return len(digits) >= 10 and digits.startswith("3")


def main():
    book = charger_book()

    with open(INPUT, "r", encoding="utf-8") as f:
        leads = list(csv.DictReader(f))

    filtered = []
    for lead in leads:
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
        phone = lead.get("Telephone", "").strip()
        website = lead.get("Site Web", "").strip()

        # NAF cible
        if naf not in ("56.10C", "56.21Z"):
            print(f"  [SKIP NAF] {nom}: {naf}")
            continue

        # Score minimum
        if score < 50:
            print(f"  [SKIP SCORE] {nom}: {score}")
            continue

        # 3+ sites
        if nb_sites < 3:
            print(f"  [SKIP SITES] {nom}: {nb_sites}")
            continue

        # Contact valide
        if not (is_valid_phone(phone) or website):
            print(f"  [SKIP CONTACT] {nom}")
            continue

        # Exclure marques
        if is_excluded_brand(nom):
            print(f"  [SKIP MARQUE] {nom}")
            continue

        # Exclure noms de personnes
        if is_person_name(nom):
            print(f"  [SKIP PERSONNE] {nom}")
            continue

        # Verification BOB (defensive)
        is_bob, match = est_dans_bob(nom, book)
        if is_bob:
            print(f"  [SKIP BOB] {nom} -> {match}")
            continue

        filtered.append(lead)

    print(f"\n{len(filtered)} leads supplementaires filtres")

    with open(OUTPUT, "w", encoding="utf-8", newline="") as f:
        if filtered:
            writer = csv.DictWriter(f, fieldnames=filtered[0].keys())
            writer.writeheader()
            writer.writerows(filtered)

    print(f"Fichier : {OUTPUT}")


if __name__ == "__main__":
    main()
