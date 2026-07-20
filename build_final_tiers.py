"""
Genere les deux fichiers finaux a partir de leads_final_croissance.csv :
- LEADS_PROKITCHES_FINAL_STRICT.csv : croissance CA positive
- LEADS_PROKITCHES_MANUAL_REVIEW.csv : sans croissance CA prouvee mais qualifies
"""

import csv
import re

INPUT_CSV = "leads_final_croissance.csv"
STRICT_CSV = "LEADS_PROKITCHES_FINAL_STRICT.csv"
MANUAL_CSV = "LEADS_PROKITCHES_MANUAL_REVIEW.csv"

SELECTED_COLS = [
    "Nom", "SIREN", "Ville", "Code Postal", "NAF",
    "Telephone", "Site Web", "Dirigeant",
    "CA", "Nb Sites", "ca_croissance_pct", "Score",
]


def main():
    with open(INPUT_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        leads = list(reader)

    strict = []
    manual = []

    for lead in leads:
        pct_str = lead.get("ca_croissance_pct", "").strip()
        try:
            pct = float(pct_str) if pct_str else None
        except ValueError:
            pct = None

        row = {col: lead.get(col, "") for col in SELECTED_COLS}

        if pct is not None and pct > 0:
            strict.append(row)
        else:
            manual.append(row)

    # Tri par croissance decroissante, puis score, puis CA
    strict.sort(key=lambda x: (
        float(x.get("ca_croissance_pct", "0") or "0"),
        int(float(x.get("Score", "0") or "0")),
        int(float(x.get("CA", "0") or "0"))
    ), reverse=True)

    manual.sort(key=lambda x: (
        int(float(x.get("Score", "0") or "0")),
        int(float(x.get("CA", "0") or "0"))
    ), reverse=True)

    for path, rows in [(STRICT_CSV, strict), (MANUAL_CSV, manual)]:
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=SELECTED_COLS)
            writer.writeheader()
            writer.writerows(rows)

    print(f"Strict (croissance positive) : {len(strict)}")
    print(f"Manual review (pas de croissance CA prouvee) : {len(manual)}")
    print(f"Total : {len(strict) + len(manual)}")


if __name__ == "__main__":
    main()
