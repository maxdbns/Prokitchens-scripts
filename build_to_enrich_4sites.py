"""
Selectionne des candidats Sirene avec 4 etablissements pour enrichissement,
en excluant les sigles, holdings, noms de personnes et marques connues.
"""
import csv
import re
from check_bob import est_dans_bob, charger_book, normaliser_nom

INPUT = "sirene_qsr_candidates.csv"
OUTPUT = "leads_to_enrich_4sites.csv"

EXCLUDED_SIRENS = {
    "378390033", "311976419", "452421332", "813725868", "801761800", "702045519",
    "478455793", "968109223", "832803639", "815183132", "339738601", "753479229",
    "823860770", "842506479", "452477656", "932455041", "834217853", "502941123",
    "531354983", "821483401", "820871085", "850864273",
}

EXCLUDED_PATTERNS = [
    r"\bGESTION\b",
    r"\bINVESTISSEMENTS\b",
    r"\bCOMPAGNIE\s+[A-Z]+\b",
    r"\bRESTAURANTS\b",
    r"\bAGENCE\b",
    r"\bCOMMUNICATIONS\b",
    r"\bDEVELOPPEMENT\s+SAS\b",
    r"\b[A-Z]\.([A-Z]\.?)+\b",  # initiales A.D.C, J.L.G
]

EXCLUDED_NAMES = {
    "ROSELYAN ANGLET SUSHI", "BBK GESTION", "SIGESS NORD", "BELKA CORP",
    "MARSEILLE PROVENCE RESTAURANTS", "PORTAFOGLIO", "CONSHIERTO", "EVRIDIKI",
    "GAMAT", "YBFM", "A D C", "JLG", "RDB 2", "HCCH", "ROSIERS ALIMENTATION",
    "ERMITAGE OPERA", "SPARTACUS", "KIMOCO", "MANDAKH", "HILO FOOD",
}

# Noms commerciaux explicitement approuves pour la liste 4 sites
ALLOWED_NAMES = {
    "QUATRE SOEURS", "FOODOJAP", "BRAVO PASTA", "FOODOBAR", "YORA PARIS",
    "STRADINA", "THE ALLEY", "LAMN SUSHI", "BABOOTEA", "GO EAT", "MOCA",
    "CRUNCHEESE", "DIMA POULET", "YOICHI", "DEEPKITCHEN", "SUWOK", "LE GAIGNE",
    "MS PATISSERIE", "BYMY",
}


def is_excluded_pattern(nom):
    n = normaliser_nom(nom)
    for pat in EXCLUDED_PATTERNS:
        if re.search(pat, n, re.I):
            return True
    for ex in EXCLUDED_NAMES:
        if ex in n or n in ex:
            return True
    return False


def is_allowed_name(nom):
    n = normaliser_nom(nom)
    for allowed in ALLOWED_NAMES:
        if allowed in n or n in allowed:
            return True
    return False


def main():
    book = charger_book()
    with open(INPUT, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    selected = []
    for r in rows:
        siren = r["siren"].strip().zfill(9)
        if siren in EXCLUDED_SIRENS:
            continue
        if int(r["nb_etablissements"]) != 4:
            continue
        if r["naf"] not in ("56.10C", "56.21Z"):
            continue
        nom = r["nom"]
        if is_excluded_pattern(nom):
            continue
        if not is_allowed_name(nom):
            continue
        if est_dans_bob(nom, book)[0]:
            continue
        selected.append({
            "Nom": nom, "SIREN": siren, "Ville": r["ville"], "Code Postal": r["code_postal"],
            "NAF": r["naf"], "Telephone": "", "Site Web": "", "Dirigeant": "",
            "CA": "", "Nb Sites": 4, "ca_croissance_pct": "", "Score": "",
            "source": "sirene_to_enrich_4sites",
        })

    print(f"{len(selected)} candidats 4 sites selectionnes")
    for s in selected:
        print(f"  + {s['Nom']}")

    with open(OUTPUT, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=selected[0].keys() if selected else [])
        writer.writeheader()
        writer.writerows(selected)


if __name__ == "__main__":
    main()
