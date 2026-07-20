"""
Verification finale des fichiers de leads ProKitchens.
Signale les doublons BOB, les contacts invalides, les exclusions manquees.
"""
import csv
import re
from check_bob import est_dans_bob, charger_book, normaliser_nom

FILES = [
    "LEADS_PROKITCHES_FINAL_STRICT.csv",
    "LEADS_PROKITCHES_MANUAL_REVIEW.csv",
    "LEADS_PROKITCHES_TO_ENRICH.csv",
]

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
    "LIDL", "ALDI", "INTERMARCHE", "BK", "BKR", "BURGER KING", "KFC", "POKE HOUSE",
    "COME", "CONCESSIONS GARES", "CONCESSIONS AEROPORTS", "PRET", "DAILY MONOP",
    "LA CROISSANTERIE", "CROISSANCE 5", "LAV'CAR", "LAV'LINGE", "INVESTISSEMENTS",
    "AGENCE TECHNOLOGIQUE", "COMMUNICATIONS", "DEVELOPPEMENT SAS", "CAFE DE FRANCE",
    "BOULANGERIES BG", "R.A.F", "R A F", "ALAIN JANIAUD", "SALIM BENYOUNES",
    "JOSUE LANOIX", "RIEM BECKER", "REX SUBS", "SOCIETE DES MAGASINS LOUIS",
    "AGTM GARES", "AGTM GARE", "RELAY", "LAGARDERE", "VINDEMIA FINANCES",
    "BOUBACAR MENDES", "VIAGIO", "ANTONIO ALVES DA SILVA", "ASHAK GABER AZIZ",
    "COTTI COFFEE", "COTTI", "KRISPY KREME", "DOUGHNUTS MANUFACTURING",
}

EXCLUDED_SIRENS = {
    "378390033", "311976419", "452421332", "813725868", "801761800", "702045519",
    "478455793", "968109223", "832803639", "815183132", "339738601", "753479229",
    "823860770", "842506479", "452477656", "932455041", "834217853", "502941123",
    "531354983", "821483401", "820871085", "850864273", "542095336", "522956440",
    "814873501", "478703226", "481533669", "512056623", "992933507",
    "831071022", "509873089", "451263511", "929369114", "899474712",
    "844556605", "751218793", "492783394", "407687243", "900617549",
    "877909960",
    "827971904", "352751200", "798070231", "333634160", "314187048",
    "799397286", "439077462", "904241957", "501620959", "792904492",
    "344379466", "894982032", "802707885", "893436527", "829609932",
    "948829262", "848553277", "941106387", "449317312", "937539963",
    "813756509", "980498901",
    "881790901",  # PRONOIA - cabinet de conseil
    "514050749",  # KITCHEN BIS - restaurant gastronomique
    "884548330",  # TPEB FOOD - cabinet de conseil
    "750800666",  # RESILIANS - renovation
    "530014398",  # TRIAXE - BTP
    "811671007",  # B2S - transport automobile
    "100409796",  # K2 KITCHEN - restaurant italien traditionnel
    "840908214",  # TFB RESEAU - boulangerie
    "849281571",  # EL CAPITAN - maison partagee
    "877909960",  # J.M - nom sigle/personne
    "791255086",  # WOK UP - O TACOS
    "809245889",  # DELEEV - livraison courses
    "953728839",  # YOICHI - whisky
    "837782945",  # THE ALLEY - bubble tea
    "900648320",  # BABOOTEA 2 - bubble tea
    "914528930",  # CRUNCHEESE - domaine en vente
    "832571517",  # GO EAT - domaine en vente
    "888613783",  # QUATRE SOEURS - boutique vetements
    "521832998",  # D'JAWA - club-concert
    "482735735",  # ENTRE PARENTHESE EP - 1 restaurant
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


def main():
    book = charger_book()
    all_leads = []
    issues = []
    sirens = set()

    for path in FILES:
        try:
            with open(path, "r", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
        except FileNotFoundError:
            continue

        for r in rows:
            siren = r.get("SIREN", "").strip().zfill(9)
            nom = r.get("Nom", "")
            naf = r.get("NAF", "")
            phone = r.get("Telephone", "")
            website = r.get("Site Web", "")
            try:
                nb = int(float(r.get("Nb Sites", "0") or "0"))
            except ValueError:
                nb = 0

            if siren in sirens:
                issues.append((path, nom, "SIREN duplique"))
            sirens.add(siren)

            if siren in EXCLUDED_SIRENS:
                issues.append((path, nom, "SIREN exclu"))

            if is_excluded_brand(nom):
                issues.append((path, nom, "Marque exclue"))

            if naf not in ("56.10C", "56.21Z"):
                issues.append((path, nom, f"NAF {naf} hors cible"))

            if nb < 3:
                issues.append((path, nom, f"Nb sites {nb} < 3"))

            is_bob, match = est_dans_bob(nom, book)
            if is_bob:
                issues.append((path, nom, f"BOB -> {match}"))

            if path != "LEADS_PROKITCHES_TO_ENRICH.csv":
                if not (is_valid_phone(phone) or website):
                    issues.append((path, nom, "Contact invalide"))

            all_leads.append(r)

    print(f"Leads verifies : {len(all_leads)}")
    print(f"Problemes trouves : {len(issues)}")
    for path, nom, reason in issues:
        print(f"  [{path}] {nom} -> {reason}")


if __name__ == "__main__":
    main()
