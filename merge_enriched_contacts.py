"""
Fusionne les contacts trouves dans Supabase/Google dans les fichiers finaux.
Les to_enrich qui ont un contact fiable sont promus en manual.
"""
import csv

ENRICHED_CSV = "LEADS_PROKITCHES_TO_ENRICH_ENRICHIS.csv"

STRICT_CSV = "LEADS_PROKITCHES_FINAL_STRICT.csv"
MANUAL_CSV = "LEADS_PROKITCHES_MANUAL_REVIEW.csv"
TOENRICH_CSV = "LEADS_PROKITCHES_TO_ENRICH.csv"
OUTPUT = "LEADS_PROKITCHES_FINAL.csv"

SELECTED_COLS = [
    "Nom", "SIREN", "Ville", "Code Postal", "NAF",
    "Telephone", "Site Web", "Dirigeant",
    "CA", "Nb Sites", "ca_croissance_pct", "Score",
]


def load_csv(path):
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_csv(path, rows, fieldnames):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    strict = load_csv(STRICT_CSV)
    manual = load_csv(MANUAL_CSV)
    to_enrich = load_csv(TOENRICH_CSV)
    enriched = {r["SIREN"].strip().zfill(9): r for r in load_csv(ENRICHED_CSV)}

    new_manual = []
    remaining_to_enrich = []

    for r in to_enrich:
        siren = r["SIREN"].strip().zfill(9)
        e = enriched.get(siren, {})
        phone = e.get("Telephone") or e.get("supabase_phone") or ""
        website = e.get("Site Web") or e.get("supabase_website") or ""

        if phone or website:
            r["Telephone"] = phone
            r["Site Web"] = website
            # Promouvoir en manual
            r["source"] = (r.get("source") or "") + "_enriched"
            new_manual.append(r)
        else:
            remaining_to_enrich.append(r)

    manual.extend(new_manual)

    # Trier
    strict.sort(key=lambda x: (
        float(x.get("ca_croissance_pct", "0") or "0"),
        int(float(x.get("Score", "0") or "0")),
        int(float(x.get("CA", "0") or "0")),
    ), reverse=True)

    manual.sort(key=lambda x: (
        int(float(x.get("Score", "0") or "0")),
        int(float(x.get("CA", "0") or "0")),
    ), reverse=True)

    remaining_to_enrich.sort(key=lambda x: int(x.get("Nb Sites", "0") or "0"), reverse=True)

    save_csv(STRICT_CSV, strict, SELECTED_COLS + ["source"])
    save_csv(MANUAL_CSV, manual, SELECTED_COLS + ["source"])
    save_csv(TOENRICH_CSV, remaining_to_enrich, SELECTED_COLS + ["source"])

    # Combiner
    all_rows = []
    for rows, status in [(strict, "strict"), (manual, "manual"), (remaining_to_enrich, "to_enrich")]:
        for r in rows:
            r["statut"] = status
            all_rows.append(r)

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

    print(f"Fusion terminee:")
    print(f"  strict: {len(strict)}")
    print(f"  manual: {len(manual)} (+{len(new_manual)} promus)")
    print(f"  to_enrich: {len(remaining_to_enrich)}")
    print(f"  total: {len(all_rows)}")


if __name__ == "__main__":
    main()
