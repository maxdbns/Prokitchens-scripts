"""
Combine les 3 fichiers finaux en un seul CSV avec une colonne statut.
"""
import csv

FILES = [
    ("data/LEADS_PROKITCHES_FINAL_STRICT.csv", "strict"),
    ("data/LEADS_PROKITCHES_MANUAL_REVIEW.csv", "manual"),
    ("data/LEADS_PROKITCHES_TO_ENRICH.csv", "to_enrich"),
]
OUTPUT = "data/LEADS_PROKITCHES_FINAL.csv"

all_rows = []
for path, status in FILES:
    with open(path, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["statut"] = status
        all_rows.append(r)

# Trier: strict, manual, to_enrich; puis par score decroissant
all_rows.sort(key=lambda x: (
    {"strict": 0, "manual": 1, "to_enrich": 2}[x["statut"]],
    -int(float(x.get("Score", "0") or "0")),
    -int(float(x.get("CA", "0") or "0")),
))

if all_rows:
    fieldnames = list(all_rows[0].keys())
    with open(OUTPUT, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

print(f"Fichier combine : {OUTPUT}")
print(f"Total : {len(all_rows)} (strict {sum(1 for r in all_rows if r['statut']=='strict')}, manual {sum(1 for r in all_rows if r['statut']=='manual')}, to_enrich {sum(1 for r in all_rows if r['statut']=='to_enrich')})")
