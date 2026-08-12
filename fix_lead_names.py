#!/usr/bin/env python3
"""Port Python de prokitchens-app/scripts/fix-lead-names.ts (incl. lib/leadNames.ts).

Corrige leads.nom à partir du nom majoritaire de ses établissements
(confiance >= 90%). Ne touche pas aux leads modifiés manuellement
(nom_legal != nom).
"""
import os
import sys
import unicodedata
import requests

BATCH_SIZE = 1000

SUPABASE_URL = os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_API_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("[fix-lead-names] Supabase credentials not configured")
    sys.exit(1)

DRY_RUN = "--dry-run" in sys.argv


def headers(prefer=None):
    h = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Accept": "application/json",
    }
    if prefer:
        h["Content-Type"] = "application/json"
        h["Prefer"] = prefer
    return h


def normalize(name: str) -> str:
    n = unicodedata.normalize("NFD", name.lower())
    n = "".join(c for c in n if unicodedata.category(c) != "Mn")
    return "".join(c for c in n if c in "abcdefghijklmnopqrstuvwxyz0123456789&").strip()


def derive_lead_name(current_nom, current_nom_legal, etab_names):
    active = [n.strip() for n in etab_names if n and n.strip()]
    if not active:
        return None

    counts = {}
    for name in active:
        key = normalize(name)
        if not key:
            continue
        if key in counts:
            counts[key]["count"] += 1
        else:
            counts[key] = {"count": 1, "original": name}

    if not counts:
        return None
    best = max(counts.items(), key=lambda kv: kv[1]["count"])
    key, value = best

    confidence = value["count"] / len(active)
    if confidence < 0.9:
        return None
    if key == normalize(current_nom or ""):
        return None

    return {
        "name": value["original"],
        "legalName": current_nom_legal or current_nom,
        "confidence": confidence,
    }


def fetch_all_etabs_by_siren():
    result = {}
    offset = 0
    while True:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/etablissements",
            params={"select": "siren,nom", "offset": offset, "limit": BATCH_SIZE},
            headers=headers(),
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data:
            break
        for e in data:
            result.setdefault(e["siren"], []).append(e.get("nom") or "")
        offset += len(data)
        if len(data) < BATCH_SIZE:
            break
    return result


def main():
    print("[fix-lead-names] Chargement des établissements...")
    etabs_by_siren = fetch_all_etabs_by_siren()
    print(f"[fix-lead-names] {len(etabs_by_siren)} SIREN avec établissements")

    corrected = skipped = processed = 0
    offset = 0

    while True:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/leads",
            params={"select": "id,siren,nom,nom_legal", "order": "id.asc",
                    "offset": offset, "limit": BATCH_SIZE},
            headers=headers(),
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data:
            break

        updates = []
        for lead in data:
            processed += 1
            names = etabs_by_siren.get(lead["siren"]) or []
            if not names:
                skipped += 1
                continue
            if lead.get("nom_legal") and lead["nom_legal"] != lead["nom"]:
                skipped += 1
                continue
            result = derive_lead_name(lead["nom"], lead.get("nom_legal"), names)
            if result:
                updates.append({"siren": lead["siren"], "nom": result["name"],
                                "nom_legal": result["legalName"]})

        if updates:
            if DRY_RUN:
                for u in updates:
                    print(f"[dry-run] {u['siren']}: \"{u['nom_legal']}\" -> \"{u['nom']}\"")
            else:
                resp = requests.post(
                    f"{SUPABASE_URL}/rest/v1/leads?on_conflict=siren",
                    json=updates,
                    headers=headers("return=minimal,resolution=merge-duplicates"),
                    timeout=120,
                )
                resp.raise_for_status()
            corrected += len(updates)
            print(f"[fix-lead-names] batch {offset}: corrected {len(updates)}")
        else:
            print(f"[fix-lead-names] batch {offset}: no corrections")

        offset += len(data)
        if len(data) < BATCH_SIZE:
            break

    print(f"[fix-lead-names] Terminé. Processed {processed}, corrected {corrected}, skipped {skipped}")


if __name__ == "__main__":
    main()
