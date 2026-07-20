"""
Nettoie LEADS_PROKITCHES_TO_ENRICH.csv en retirant les candidats non pertinents
(holdings, noms de personnes, marques connues, sigles obscurs, non-restaurant).
"""
import csv
import re
from check_bob import charger_book, est_dans_bob, normaliser_nom

INPUT = "LEADS_PROKITCHES_TO_ENRICH.csv"
OUTPUT = "LEADS_PROKITCHES_TO_ENRICH_CLEAN.csv"

EXCLUDED_SIRENS = {
    "378390033",  # MONOP'DAILY (Monoprix)
    "311976419",  # LA CROISSANTERIE ILE DE FRANCE
    "452421332",  # MH INVESTISSEMENTS (LAV'CAR LAV'LINGE)
    "813725868",  # CROISSANCE 5 = L'Avant Comptoir de la Mer (56.10A)
    "801761800",  # LILLE DEVELOPPEMENT SAS
    "702045519",  # CAFE DE FRANCE (trop generique)
    "478455793",  # BOULANGERIES BG (B B G) - boulangerie
    "968109223",  # ALAIN JANIAUD
    "832803639",  # SALIM BENYOUNES
    "815183132",  # JOSUE LANOIX
    "339738601",  # RIEM BECKER
    "753479229",  # R.A.F
}

EXCLUDED_PATTERNS = [
    r"MONOP['\s]?DAILY",
    r"MONOPRIX",
    r"LA CROISSANTERIE",
    r"LAV['\s]?CAR",
    r"LAV['\s]?LINGE",
    r"INVESTISSEMENTS",
    r"AGENCE TECHNOLOGIQUE",
    r"COMMUNICATIONS\s*\(ATC\)",
    r"COMMUNICATIONS$",
    r"DEVELOPPEMENT SAS$",
    r"CAFE DE FRANCE$",
    r"BOULANGERIES BG",
    r"R\.A\.F$",
    r"CROISSANCE 5$",
]

EXCLUDED_NAMES = {
    "ALAIN JANIAUD",
    "SALIM BENYOUNES",
    "JOSUE LANOIX",
    "RIEM BECKER",
    "CAFE DE FRANCE",
    "CROISSANCE 5",
    "LILLE DEVELOPPEMENT SAS",
    "MH INVESTISSEMENTS",
    "AGENCE TECHNOLOGIQUE DE COMMUNICATIONS",
}


def is_excluded_by_pattern(nom):
    n = normaliser_nom(nom)
    for pat in EXCLUDED_PATTERNS:
        if re.search(pat, n, re.I):
            return True
    return False


def is_excluded_by_name(nom):
    n = normaliser_nom(nom)
    for ex in EXCLUDED_NAMES:
        if ex in n or n in ex:
            return True
    return False


def main():
    book = charger_book()

    rows = list(csv.DictReader(open(INPUT, "r", encoding="utf-8")))
    clean = []
    removed = []

    for r in rows:
        siren = (r.get("SIREN") or "").strip().zfill(9)
        nom = r.get("Nom", "")
        n = normaliser_nom(nom)

        reason = None
        if siren in EXCLUDED_SIRENS:
            reason = "SIREN exclu"
        elif is_excluded_by_pattern(nom) or is_excluded_by_name(nom):
            reason = "nom exclu"
        elif est_dans_bob(nom, book)[0]:
            reason = "BOB"

        if reason:
            removed.append((nom, reason))
        else:
            clean.append(r)

    print(f"Retire {len(removed)} candidats :")
    for nom, reason in removed:
        print(f"  [{reason}] {nom}")

    print(f"\nReste {len(clean)} candidats a enrichir")

    with open(OUTPUT, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys() if rows else [])
        writer.writeheader()
        writer.writerows(clean)

    print(f"Fichier : {OUTPUT}")


if __name__ == "__main__":
    main()
