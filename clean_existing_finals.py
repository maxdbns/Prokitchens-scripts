"""
Nettoie les fichiers finaux existants en retirant les leads presents dans le BOB
et les marques connues a exclure manuellement.
"""
import csv
from check_bob import est_dans_bob, charger_book

INPUTS = [
    ("data/LEADS_PROKITCHES_FINAL_STRICT.csv", "strict"),
    ("data/LEADS_PROKITCHES_MANUAL_REVIEW.csv", "manual"),
]
OUTPUT = "data/leads_existing_clean.csv"

# Marques connues a exclure meme si le matching automatique ne les detecte pas
# (noms d'entites juridiques differentes du nom commercial)
EXCLUDED_NAMES = {
    "MC DONALD'S", "MC DONALD S", "MCDONALD'S", "MCDONALDS", "MCDONALD",
    "PRET (FRANCE)", "PRET A MANGER", "PRETAMANGER",
    "LA BRIOCHE DOREE", "BRIOCHE DOREE",
    "POKAWA MONTORGUEIL", "POKAWA",
}


def is_excluded(nom):
    n = nom.upper().replace("'", " ").replace("-", " ").strip()
    for ex in EXCLUDED_NAMES:
        if ex in n or n in ex:
            return True
    return False


book = charger_book()
print(f"{len(book)} noms dans le BOB")

cleaned = []
for path, tier in INPUTS:
    with open(path, "r", encoding="utf-8") as f:
        leads = list(csv.DictReader(f))

    for lead in leads:
        nom = lead.get("Nom", "")
        if is_excluded(nom):
            print(f"  [EXCLU MANUEL] {nom}")
            continue

        is_bob, match = est_dans_bob(nom, book)
        if is_bob:
            print(f"  [EXCLU BOB] {nom} -> {match}")
            continue

        lead["tier"] = tier
        cleaned.append(lead)

print(f"\n{len(cleaned)} leads existants propres")

with open(OUTPUT, "w", encoding="utf-8", newline="") as f:
    if cleaned:
        fieldnames = list(cleaned[0].keys())
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(cleaned)

print(f"Fichier : {OUTPUT}")
