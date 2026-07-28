"""
Re-verifie tous les leads finaux via l'API Sirene et exclut ceux dont:
- NAF n'est pas 56.10C ou 56.21Z
- nb_etablissements_ouverts < 3
- concept non pertinent (caviar, glacier, salon de the, bar, holding...)
"""
import csv
import requests
import time
from check_bob import est_dans_bob, charger_book, normaliser_nom

API_URL = "https://recherche-entreprises.api.gouv.fr/search"

INPUTS = {
    "data/LEADS_PROKITCHES_FINAL_STRICT.csv": "strict",
    "data/LEADS_PROKITCHES_MANUAL_REVIEW.csv": "manual",
    "data/LEADS_PROKITCHES_TO_ENRICH.csv": "to_enrich",
}

OUTPUT_STRICT = "data/LEADS_PROKITCHES_FINAL_STRICT.csv"
OUTPUT_MANUAL = "data/LEADS_PROKITCHES_MANUAL_REVIEW.csv"
OUTPUT_TOENRICH = "data/LEADS_PROKITCHES_TO_ENRICH.csv"
OUTPUT_COMBINED = "data/LEADS_PROKITCHES_FINAL.csv"

EXCLUDED_SIRENS = {
    "378390033", "311976419", "452421332", "813725868", "801761800", "702045519",
    "478455793", "968109223", "832803639", "815183132", "339738601", "753479229",
    "823860770", "842506479", "452477656", "932455041", "834217853", "502941123",
    "531354983", "821483401", "820871085", "850864273", "992933507", "831071022",
    "509873089", "451263511", "929369114", "899474712", "844556605", "751218793",
    "492783394", "407687243", "900617549", "877909960", "827971904", "352751200",
    "798070231", "333634160", "314187048", "799397286", "439077462", "904241957",
    "501620959", "792904492", "344379466", "894982032", "802707885", "893436527",
    "829609932", "948829262", "848553277", "941106387", "449317312", "937539963",
    "813756509", "980498901",
    # Faux positifs verifies par site web / Sirene
    "944071224",  # GRAINS DE FOLIE - boulangerie
    "817795768",  # KENTARINE - restaurant gastronomique
    "921598421",  # LA RECETTE FRANCE - ecole de cuisine
    "439280090",  # G & G CHOISEUL - figurines (fioko.shop)
    "823398631",  # GROUPE MTG - cartes a collectionner (fuji-store.fr)
    "450607494",  # RESILIANS DSC - doublon RESILIANS
    "799400767",  # GIVREE BOUTIQUES - glacier
    "807469317",  # BALUCHON A TABLE CITOYENS - association/collectivite
    "794551341",  # AMUNDSEN FRANCE - brasserie (Comptoir Belge)
    "925070229",  # MOCA - sigle
    "907734198",  # SPINACH MFCO - sigle
    "881790901",  # PRONOIA - cabinet de conseil, pas restauration
    "514050749",  # KITCHEN BIS - restaurant gastronomique (Ze Kitchen Galerie)
    "884548330",  # TPEB FOOD - cabinet de conseil (Tomorrow Food), pas enseigne
    "750800666",  # RESILIANS - entreprise de renovation (pas restauration)
    "530014398",  # TRIAXE - societe de conseil BTP (pas restauration)
    "811671007",  # B2S - convoyage automobile (pas restauration)
    "100409796",  # K2 KITCHEN - restaurant italien traditionnel (pas QSR)
    "840908214",  # TFB RESEAU - boulangerie French Bastards (pas QSR)
    "849281571",  # EL CAPITAN - site web = maison partagee/association, pas restaurant
    "877909960",  # J.M - nom sigle/personne, pas une enseigne identifiable
    "791255086",  # WOK UP - enseigne O TACOS (marque exclue)
    "809245889",  # DELEEV (LA BELLE VIE) - service de livraison de courses, pas restaurant
    "953728839",  # YOICHI - redirige vers whisky.fr (whisky, pas restauration)
    "837782945",  # THE ALLEY - chaine de bubble tea / boissons
    "900648320",  # BABOOTEA 2 - bubble tea
    "914528930",  # CRUNCHEESE - domaine en vente, pas de site actif
    "832571517",  # GO EAT - domaine en vente, pas de site actif
    "888613783",  # QUATRE SOEURS - site soeur.fr = boutique de vetements
    "521832998",  # D'JAWA - site la-java.fr = club-concert (pas restaurant)
    "482735735",  # ENTRE PARENTHESE EP - site parenthesebrunch.com = 1 restaurant (pas 21 sites)
}

EXCLUDED_BRANDS = {
    "COTTI COFFEE", "COTTI", "KRISPY KREME", "DOUGHNUTS MANUFACTURING",
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
}

NON_QSR_KEYWORDS = [
    "CAVIAR", "GLACIER", "GELATO", "SALON DE THE", "MARIAGE FRERES", "ESCARGOT",
    "BOULANGERIE", "PATISSERIE", "CROISSANTERIE", "HOLDING", "FINANCES", "INVESTISSEMENTS",
    "RETAIL", "TECH", "GARES", "HOPITAL", "BAR ", "BAR$", "BRASSERIE", "BISTROT",
    "CENACLE", "ECOLE DE CUISINE", "CUISINE PARIS", "GALERIE", "MANICOTTI",
    "BIJOUTERIE", "JOAILLERIE", "CLOTHING", "VETEMENT", "SAVOYARD",
]


def is_excluded_brand(nom):
    n = normaliser_nom(nom)
    for brand in EXCLUDED_BRANDS:
        if normaliser_nom(brand) in n:
            return True
    return False


def is_non_qsr(nom):
    import re
    n = normaliser_nom(nom)
    for kw in NON_QSR_KEYWORDS:
        if re.search(rf"\b{re.escape(kw)}\b", n, re.I) or kw in n:
            return True
    return False


def fetch_sirene(siren, retries=3):
    for attempt in range(retries):
        try:
            r = requests.get(API_URL, params={"q": siren}, timeout=10)
            r.raise_for_status()
            data = r.json()
            results = data.get("results", [])
            if not results:
                return None
            return results[0]
        except Exception as e:
            if attempt == retries - 1:
                print(f"  Erreur API {siren}: {e}")
                return None
            time.sleep(1.5 * (2 ** attempt))
    return None


def process_leads(path, status):
    with open(path, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    kept = []
    removed = []
    for r in rows:
        siren = r.get("SIREN", "").strip().zfill(9)
        nom = r.get("Nom", "")

        if siren in EXCLUDED_SIRENS:
            removed.append((nom, "SIREN exclu"))
            continue
        if is_excluded_brand(nom):
            removed.append((nom, "Marque exclue"))
            continue

        # Appel API Sirene
        res = fetch_sirene(siren)
        if not res:
            removed.append((nom, "API Sirene indisponible"))
            continue

        naf = res.get("activite_principale", "")
        nb_sites = res.get("nombre_etablissements_ouverts", 0) or 0
        sirene_nom = res.get("nom_complet", "") or res.get("nom_raison_sociale", "") or nom

        if naf not in ("56.10C", "56.21Z"):
            removed.append((nom, f"NAF {naf} hors cible"))
            continue
        if int(nb_sites) < 3:
            removed.append((nom, f"{nb_sites} sites < 3"))
            continue
        if is_non_qsr(sirene_nom) or is_non_qsr(nom):
            removed.append((nom, f"Concept non QSR ({sirene_nom})"))
            continue

        # Mettre a jour le nom et nb sites avec Sirene
        r["Nom"] = sirene_nom
        r["Nb Sites"] = nb_sites
        kept.append(r)
        time.sleep(0.6)

    return kept, removed


def main():
    book = charger_book()

    all_kept = {"strict": [], "manual": [], "to_enrich": []}
    all_removed = []

    for path, status in INPUTS.items():
        print(f"\nTraitement {path} ({status})")
        kept, removed = process_leads(path, status)
        all_kept[status] = kept
        all_removed.extend([(path, nom, reason) for nom, reason in removed])
        print(f"  Gardes : {len(kept)} | Retires : {len(removed)}")

    print(f"\n=== TOTAL RETIRES : {len(all_removed)} ===")
    for path, nom, reason in all_removed:
        print(f"  [{path}] {nom} -> {reason}")

    # Sauvegarder
    for path, status in [(OUTPUT_STRICT, "strict"), (OUTPUT_MANUAL, "manual"), (OUTPUT_TOENRICH, "to_enrich")]:
        rows = all_kept[status]
        if rows:
            with open(path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
        else:
            open(path, "w", encoding="utf-8").close()

    # Combiner
    combined = []
    for status, rows in [("strict", all_kept["strict"]), ("manual", all_kept["manual"]), ("to_enrich", all_kept["to_enrich"])]:
        for r in rows:
            r["statut"] = status
            combined.append(r)

    combined.sort(key=lambda x: (
        {"strict": 0, "manual": 1, "to_enrich": 2}[x["statut"]],
        -int(float(x.get("Score", "0") or "0")),
    ))

    if combined:
        with open(OUTPUT_COMBINED, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=combined[0].keys())
            writer.writeheader()
            writer.writerows(combined)

    print(f"\n=== TOTAL FINAL : {len(combined)} ===")
    print(f"  strict: {len(all_kept['strict'])}, manual: {len(all_kept['manual'])}, to_enrich: {len(all_kept['to_enrich'])}")


if __name__ == "__main__":
    main()
