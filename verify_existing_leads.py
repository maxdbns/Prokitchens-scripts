"""
Verifie les leads finaux existants contre le BOB avec matching strict.
"""
import csv
from check_bob import est_dans_bob, charger_book

FILES = [
    "LEADS_PROKITCHES_FINAL_STRICT.csv",
    "LEADS_PROKITCHES_MANUAL_REVIEW.csv",
]

book = charger_book()
print(f"{len(book)} noms dans le BOB")

for path in FILES:
    print(f"\n=== {path} ===")
    with open(path, "r", encoding="utf-8") as f:
        leads = list(csv.DictReader(f))

    in_bob = []
    hors_bob = []
    for lead in leads:
        nom = lead.get("Nom", "")
        is_bob, match = est_dans_bob(nom, book)
        if is_bob:
            in_bob.append({**lead, "match_bob": match})
            print(f"  [BOB] {nom} -> {match}")
        else:
            hors_bob.append(lead)
            print(f"  [OK] {nom}")

    print(f"  Total: {len(leads)} | BOB: {len(in_bob)} | OK: {len(hors_bob)}")
