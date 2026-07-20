"""
Retire les leads automatiquement ajoutes non pertinents du manual review.
"""
import csv

INPUT = "LEADS_PROKITCHES_MANUAL_REVIEW.csv"
OUTPUT = "LEADS_PROKITCHES_MANUAL_REVIEW.csv"

EXCLUDED_SIRENS = {
    "542095336",  # RELAY / LAGARDERE
    "522956440",  # VINDEMIA FINANCES (holding, site gouv.fr)
    "814873501",  # BOUBACAR MENDES (hôpital)
    "478703226",  # VIAGIO (Opera de Paris)
    "481533669",  # ANTONIO ALVES DA SILVA (real estate)
    "512056623",  # ASHAK GABER AZIZ
}


with open(INPUT, "r", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

kept = [r for r in rows if r.get("SIREN", "").strip().zfill(9) not in EXCLUDED_SIRENS]
removed = len(rows) - len(kept)
print(f"Retire {removed} leads du manual review")

with open(OUTPUT, "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(kept)

print(f"Manual review total : {len(kept)}")
