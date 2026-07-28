"""
Construit les fichiers finaux de leads ProKitchens.
- STRICT : croissance CA positive prouvee
- MANUAL : qualifies mais sans croissance CA prouvee
- TO_ENRICH : candidats Sirene interessants a verifier/enrichir
"""
import csv
import re
from check_bob import est_dans_bob, charger_book, normaliser_nom

SOURCES = [
    ("data/leads_existing_clean.csv", None),
    ("data/leads_supplementaires_filtered.csv", "supplementaire"),
    ("data/leads_final_pool.csv", "enrichi"),
]

SIRENE_CSV = "data/sirene_qsr_candidates.csv"

STRICT_CSV = "data/LEADS_PROKITCHES_FINAL_STRICT.csv"
MANUAL_CSV = "data/LEADS_PROKITCHES_MANUAL_REVIEW.csv"
TO_ENRICH_CSV = "data/LEADS_PROKITCHES_TO_ENRICH.csv"
TO_ENRICH_4SITES = "data/leads_to_enrich_4sites.csv"

SELECTED_COLS = [
    "Nom", "SIREN", "Ville", "Code Postal", "NAF",
    "Telephone", "Site Web", "Dirigeant",
    "CA", "Nb Sites", "ca_croissance_pct", "Score",
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
    "DAILYMONOP", "AMREST", "BURGER KING", "KFC", "FOODCHERI", "LENOTRE",
    "POTEL & CHABOT", "DALLOYAU", "GARES SNCF", "SNCF", "AUCHAN", "CARREFOUR",
    "CASINO", "MONOPRIX", "FRANPRIX", "LECLERC", "LIDL", "ALDI", "INTERMARCHE",
    "BK", "BKR", "BURGER KING", "KFC", "POKE HOUSE", "COME", "CONCESSIONS GARES",
    "CONCESSIONS AEROPORTS", "PRET", "PRETAMANGER", "DAILYMONOP", "DAILY MONOP", "MONOPRIX",
    "LA CROISSANTERIE", "CROISSANCE 5", "LAV'CAR", "LAV'LINGE", "INVESTISSEMENTS",
    "AGENCE TECHNOLOGIQUE", "COMMUNICATIONS", "DEVELOPPEMENT SAS", "CAFE DE FRANCE",
    "BOULANGERIES BG", "R.A.F", "R A F", "ALAIN JANIAUD", "SALIM BENYOUNES",
    "JOSUE LANOIX", "RIEM BECKER", "REX SUBS", "SOCIETE DES MAGASINS LOUIS",
    "AGTM GARES", "AGTM GARE", "COTTI COFFEE", "COTTI", "KRISPY KREME", "DOUGHNUTS MANUFACTURING",
}

# SIRENs identifies comme non pertinents ou doublons (ex: GN FRANCE vs GN FRANCE 2022)
EXCLUDED_SIRENS = {
    "378390033",  # MONOP'DAILY
    "311976419",  # LA CROISSANTERIE ILE DE FRANCE
    "452421332",  # MH INVESTISSEMENTS (LAV'CAR LAV'LINGE)
    "813725868",  # CROISSANCE 5 / L'Avant Comptoir de la Mer
    "801761800",  # LILLE DEVELOPPEMENT SAS
    "702045519",  # CAFE DE FRANCE
    "478455793",  # BOULANGERIES BG
    "968109223",  # ALAIN JANIAUD
    "832803639",  # SALIM BENYOUNES
    "815183132",  # JOSUE LANOIX
    "339738601",  # RIEM BECKER
    "753479229",  # R.A.F
    "823860770",  # GN FRANCE (doublon avec GN FRANCE 2022 / 910688225)
    "842506479",  # AGTM GARES
    "452477656",  # SOCIETE DES MAGASINS LOUIS
    "932455041",  # REX SUBS FRANCE
    "834217853",  # R2C (sigle obscur)
    "502941123",  # SMBPC (sigle obscur)
    "531354983",  # KDSUSHI0002 (sigle technique)
    "821483401",  # TKPF (sigle obscur)
    "820871085",  # I2R (sigle obscur)
    "850864273",  # CABJ770 (sigle technique)
    "992933507",  # COTTI COFFEE FRANCE (deja dans BOB)
    "831071022",  # PICTO CONNEXIONS (labo photo, pas restauration)
    "509873089",  # G. & G. BERRI (boulangerie)
    "451263511",  # G ET G SAINT HONORE (boulangerie)
    "929369114",  # ICR RETAIL (retail)
    "899474712",  # ONEWORLD TECH (MALABARE) (tech)
    "844556605",  # MULHOUSE 55 (nom de ville+chiffre)
    "751218793",  # TERA (TR) (sigle)
    "492783394",  # HVM PIZZA (sigle)
    "407687243",  # MACHARA (MCA) (sigle)
    "900617549",  # DANH-NGHIEP (nom de personne)
    "877909960",  # J.M (nom sigle/personne)
    # Suspects spots-check + faux positifs matching inverse BOB
    "827971904",  # I-LUNCH
    "352751200",  # MEDIANCE
    "798070231",  # HAVEAGOODAY
    "333634160",  # SOGOOD
    "314187048",  # TOUT CHAUD
    "799397286",  # SO'GEREST
    "439077462",  # WHATEVER
    "904241957",  # PERENNE
    "501620959",  # AGAKING EXPLOITATION
    "792904492",  # GOZAP
    "344379466",  # ACTAL
    "894982032",  # BINTJE!
    "802707885",  # LPDS TEAM
    "893436527",  # INIMITABLE
    "829609932",  # DESIREE
    "948829262",  # DAKGO
    "848553277",  # SIMTAY
    "941106387",  # LES RESTAURANTS BISTROT SOLEIL
    "449317312",  # REGAL DES ILES (faux positif matching BOB)
    "937539963",  # SUSHI LE 1984 (faux positif matching BOB)
    "813756509",  # LAMN SUSHI SAS (match BOB sur SUSHI generique)
    "980498901",  # DOUGHNUTS MANUFACTURING & RETAIL (Krispy Kreme, deja client)
    "881790901",  # PRONOIA - cabinet de conseil
    "514050749",  # KITCHEN BIS - restaurant gastronomique (Ze Kitchen Galerie)
    "884548330",  # TPEB FOOD - cabinet de conseil
    "750800666",  # RESILIANS - renovation
    "530014398",  # TRIAXE - BTP
    "811671007",  # B2S - transport automobile
    "100409796",  # K2 KITCHEN - restaurant italien traditionnel
    "840908214",  # TFB RESEAU - boulangerie
    "849281571",  # EL CAPITAN - maison partagee
    "877909960",  # J.M - nom sigle/personne, pas une enseigne identifiable
    "791255086",  # WOK UP - enseigne O TACOS (marque exclue)
    "809245889",  # DELEEV (LA BELLE VIE) - livraison de courses
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


def normalize_row(row, source_tag=None):
    """Normalise une ligne vers les colonnes selectionnees."""
    out = {}
    for col in SELECTED_COLS:
        val = row.get(col, "")
        if col == "Nom" and not val:
            val = row.get("nom", "")
        if col == "SIREN" and not val:
            val = row.get("siren", "")
        if col == "Ville" and not val:
            val = row.get("ville", "")
        if col == "Code Postal" and not val:
            val = row.get("code_postal", "")
        if col == "NAF" and not val:
            val = row.get("naf", "")
        if col == "Telephone" and not val:
            val = row.get("google_phone", "")
        if col == "Site Web" and not val:
            val = row.get("google_website", "")
        if col == "Dirigeant" and not val:
            val = row.get("dirigeant", "")
        if col == "CA" and not val:
            val = row.get("ca", "")
        if col == "Nb Sites" and not val:
            val = row.get("nb_sites", "") or row.get("nb_etablissements", "")
        if col == "ca_croissance_pct" and not val:
            val = row.get("croissance_ca", "")
        if col == "Score" and not val:
            val = row.get("score", "")
        out[col] = val

    if source_tag:
        out["source"] = source_tag
    return out


def parse_growth_pct(val):
    if not val or str(val).strip() == "":
        return None
    try:
        return float(str(val).strip())
    except ValueError:
        return None


def main():
    book = charger_book()

    # 1. Fusionner les sources
    all_leads = []
    seen_sirens = set()

    for path, tag in SOURCES:
        try:
            with open(path, "r", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
        except FileNotFoundError:
            continue

        for row in rows:
            siren = (row.get("SIREN") or row.get("siren") or "").strip().zfill(9)
            if siren in seen_sirens:
                continue
            if siren in EXCLUDED_SIRENS:
                print(f"  [EXCLU SIREN] {row.get('Nom', '') or row.get('nom', '')}")
                continue
            nom = row.get("Nom", "") or row.get("nom", "")
            if is_excluded_brand(nom):
                print(f"  [EXCLU MARQUE] {nom}")
                continue
            seen_sirens.add(siren)
            all_leads.append(normalize_row(row, tag))

    print(f"Total leads fusionnes : {len(all_leads)}")

    # 2. Diviser en strict / manual
    strict = []
    manual = []

    for lead in all_leads:
        pct = parse_growth_pct(lead.get("ca_croissance_pct", ""))
        if pct is not None and pct > 0:
            strict.append(lead)
        else:
            manual.append(lead)

    strict.sort(key=lambda x: (
        parse_growth_pct(x.get("ca_croissance_pct", "0") or "0") or 0,
        int(float(x.get("Score", "0") or "0")),
        int(float(x.get("CA", "0") or "0"))
    ), reverse=True)

    manual.sort(key=lambda x: (
        int(float(x.get("Score", "0") or "0")),
        int(float(x.get("CA", "0") or "0"))
    ), reverse=True)

    for path, rows in [(STRICT_CSV, strict), (MANUAL_CSV, manual)]:
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=SELECTED_COLS + ["source"])
            writer.writeheader()
            writer.writerows(rows)

    print(f"Strict : {len(strict)} | Manual : {len(manual)}")

    # 3. Selectionner des candidats Sirene a enrichir
    with open(SIRENE_CSV, "r", encoding="utf-8") as f:
        sirene = list(csv.DictReader(f))

    to_enrich = []
    for r in sirene:
        siren = r["siren"].strip().zfill(9)
        if siren in seen_sirens:
            continue
        if siren in EXCLUDED_SIRENS:
            continue
        nom = r["nom"]
        if is_excluded_brand(nom):
            continue
        try:
            nb = int(r["nb_etablissements"])
        except ValueError:
            nb = 0
        if nb < 5:
            continue
        naf = r["naf"]
        if naf not in ("56.10C", "56.21Z"):
            continue

        is_bob, match = est_dans_bob(nom, book)
        if is_bob:
            continue

        to_enrich.append({
            "Nom": nom,
            "SIREN": siren,
            "Ville": r["ville"],
            "Code Postal": r["code_postal"],
            "NAF": naf,
            "Telephone": "",
            "Site Web": "",
            "Dirigeant": "",
            "CA": "",
            "Nb Sites": nb,
            "ca_croissance_pct": "",
            "Score": "",
            "source": "sirene_to_enrich",
        })

    to_enrich.sort(key=lambda x: int(x["Nb Sites"]), reverse=True)

    # Ajouter les candidats 4 sites pre-approuves
    try:
        with open(TO_ENRICH_4SITES, "r", encoding="utf-8") as f:
            four_sites = list(csv.DictReader(f))
    except FileNotFoundError:
        four_sites = []

    seen_to_enrich = {r["SIREN"].strip().zfill(9) for r in to_enrich}
    for r in four_sites:
        siren = r["SIREN"].strip().zfill(9)
        if siren in EXCLUDED_SIRENS:
            continue
        if siren not in seen_to_enrich:
            to_enrich.append(r)
            seen_to_enrich.add(siren)

    to_enrich.sort(key=lambda x: int(x["Nb Sites"]), reverse=True)
    to_enrich = to_enrich[:100]

    with open(TO_ENRICH_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SELECTED_COLS + ["source"])
        writer.writeheader()
        writer.writerows(to_enrich)

    print(f"To enrich : {len(to_enrich)}")
    print(f"Total potentiel (qualifies + a enrichir) : {len(all_leads) + len(to_enrich)}")


if __name__ == "__main__":
    main()
