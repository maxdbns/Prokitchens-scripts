"""
Recherche d'entreprises QSR (NAF 56.10C et 56.21Z) avec 3+ etablissements ouverts
en Ile-de-France via l'API publique recherche-entreprises.api.gouv.fr.
Exclut le BOB Salesforce et les marques connues.
"""

import csv
import requests
import time
from check_bob import est_dans_bob, charger_book, normaliser_nom

API_URL = "https://recherche-entreprises.api.gouv.fr/search"
DEPARTEMENTS_IDF = ["75", "77", "78", "91", "92", "93", "94", "95"]
NAFS = ["56.10C", "56.21Z"]
MIN_ETABLISSEMENTS = 3
PER_PAGE = 25
MAX_PAGES = 10
OUTPUT = "data/sirene_qsr_candidates.csv"

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
    "PASTA PIZZA", "PITAYA", "POKAWA", "THA", "THAI", "PIZZA HUT",
    "TACOS AVENUE", "TACOS KING", "NEW SCHOOL TACOS", "TORTILLA", "CHIPOTLE",
    "KIMCHI", "DIM SUM", "BAO BAO", "WOK TO WALK", "RAMEN", "SUSHI BAR",
}


def is_excluded_brand(nom):
    n = normaliser_nom(nom)
    for brand in EXCLUDED_BRANDS:
        if normaliser_nom(brand) in n:
            return True
    return False


def fetch_sirene(naf, departement, page):
    params = {
        "q": "",
        "activite_principale": naf,
        "departement": departement,
        "nombre_etablissements_ouvert": f"{MIN_ETABLISSEMENTS}-",
        "page": page,
        "per_page": PER_PAGE,
    }
    try:
        resp = requests.get(API_URL, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Erreur API {naf} {departement} page {page}: {e}")
        return None


def parse_results(data):
    results = []
    for r in data.get("results", []):
        siege = r.get("siege", {})
        results.append({
            "siren": r.get("siren", ""),
            "nom": r.get("nom_complet", ""),
            "nom_raison_sociale": r.get("nom_raison_sociale", ""),
            "naf": r.get("activite_principale", ""),
            "nb_etablissements": r.get("nombre_etablissements_ouverts", 0) or r.get("nombre_etablissements", 0),
            "ville": siege.get("libelle_commune", ""),
            "code_postal": siege.get("code_postal", ""),
            "adresse": " ".join(filter(None, [
                siege.get("numero_voie", ""),
                siege.get("type_voie", ""),
                siege.get("libelle_voie", ""),
            ])),
            "departement": siege.get("departement", ""),
        })
    return results


def main():
    book = charger_book()
    print(f"{len(book)} noms dans le BOB")

    all_results = []
    for naf in NAFS:
        for dep in DEPARTEMENTS_IDF:
            for page in range(1, MAX_PAGES + 1):
                print(f"Recherche NAF={naf} Dep={dep} Page={page}")
                data = fetch_sirene(naf, dep, page)
                if not data:
                    break
                results = parse_results(data)
                if not results:
                    break
                all_results.extend(results)
                print(f"  {len(results)} resultats")
                if len(results) < PER_PAGE:
                    break
                time.sleep(0.2)

    print(f"\nTotal brut : {len(all_results)}")

    # Deduplication par SIREN
    by_siren = {}
    for r in all_results:
        siren = r["siren"]
        if siren not in by_siren or r["nb_etablissements"] > by_siren[siren]["nb_etablissements"]:
            by_siren[siren] = r

    deduped = list(by_siren.values())
    print(f"Apres dedup SIREN : {len(deduped)}")

    # Exclusions
    candidates = []
    for r in deduped:
        nom = r["nom"]
        if is_excluded_brand(nom):
            print(f"  [EXCLU MARQUE] {nom}")
            continue

        is_bob, match = est_dans_bob(nom, book)
        if is_bob:
            print(f"  [EXCLU BOB] {nom} -> {match}")
            continue

        candidates.append(r)

    # Tri par nombre d'etablissements decroissant
    candidates.sort(key=lambda x: x["nb_etablissements"], reverse=True)

    print(f"\nCandidats finaux : {len(candidates)}")

    with open(OUTPUT, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["siren", "nom", "nom_raison_sociale", "naf", "nb_etablissements", "ville", "code_postal", "adresse", "departement"])
        writer.writeheader()
        writer.writerows(candidates)

    print(f"Fichier : {OUTPUT}")


if __name__ == "__main__":
    main()
