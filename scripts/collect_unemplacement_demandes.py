"""Collecte des recherches UnEmplacement (Île-de-France) → ingestion ProFoods.

Usage:
  export UNEMPLACEMENT_EMAIL=... UNEMPLACEMENT_PASSWORD=...
  python3 scripts/collect_unemplacement_demandes.py [--push] [--all-activities]

Sans --push : mode dry-run, sauvegarde le JSON brut et affiche le résumé.
"""
import argparse
import json
import os
import re
import sys
import time

import requests

FIREBASE_API_KEY = "AIzaSyBrV4UUSZyoEmUGeWYOT8JmVNCNps0-tBk"
API_URL = "https://api.app.unemplacement.com/member_api/fetch_prospections"
STATE = "Île-de-France"
HITS_PER_PAGE = 20

FOOD_KEYWORDS = re.compile(
    r"restaur|aliment|boulanger|pâtisser|patisser|traiteur|boucher|charcut|fromag|"
    r"poisson|café|cafe|coffee|bar\b|brasserie|snack|fast|pizzeria|épicerie|epicerie|"
    r"supérette|superette|supermarché|supermarche|glacier|sandwich|sushi|kebab|food|"
    r"crêperie|creperie|bistro|cantine|dark.?kitchen|cloud.?kitchen",
    re.I,
)

EMAIL = os.environ.get("UNEMPLACEMENT_EMAIL", "")
PASSWORD = os.environ.get("UNEMPLACEMENT_PASSWORD", "")
PUSH_URL = os.environ.get(
    "PROFOODS_API_URL", "https://prokitchens-three.vercel.app/api/profoods/ingest"
)


def get_id_token() -> str:
    r = requests.post(
        f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}",
        json={"returnSecureToken": True, "email": EMAIL, "password": PASSWORD},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["idToken"]


def fetch_page(token: str, page: int) -> list:
    r = requests.post(
        API_URL,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "state": STATE,
            "locations": [],
            "filters": {
                "prospectionType": 1,
                "commercialMinSurface": "",
                "commercialMaxSurface": "",
                "commercialActivityTypes": [],
                "commercialStatusesV2": [],
                "typeFilter": [],
                "query": "",
                "commercialPlaceTypes": [],
                "search_criteria": None,
                "research_locations": [],
                "match_all_locations": True,
            },
            "page": page,
            "hits_per_page": HITS_PER_PAGE,
            "reload_all": False,
            "cached_list_new": None,
            "version": 2,
        },
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def activity_label(it: dict) -> str:
    acts = it.get("v2/admin-activite-recherchee/activite-recherchee/activity") or []
    names = [a.get("name", "") for a in acts if isinstance(a, dict)]
    return ", ".join(n for n in names if n)


def surface_range(it: dict):
    ts = it.get("total_surface") or {}
    smin = ts.get("min") or it.get("rest_surface", {}).get("min") or it.get("groundfloor_surface", {}).get("min")
    smax = ts.get("max") or it.get("rest_surface", {}).get("max") or it.get("groundfloor_surface", {}).get("max")
    try:
        smin = int(float(smin)) if smin not in (None, "") else 0
    except (ValueError, TypeError):
        smin = 0
    try:
        smax = int(float(smax)) if smax not in (None, "") else None
    except (ValueError, TypeError):
        smax = None
    return smin, smax


def loyer_max(it: dict):
    v = it.get("v2/location-ou-achat/loyer-maximum/loyer-maximum")
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def map_demande(it: dict) -> dict:
    locs = it.get("locations") or []
    loc_names = [l.get("nom") for l in locs if isinstance(l, dict) and l.get("nom")]
    ville = loc_names[0] if loc_names else STATE
    smin, smax = surface_range(it)
    act = activity_label(it)
    statut = (it.get("user_status_v2") or "").replace("-", " ")
    zones = ", ".join(loc_names[1:6]) if len(loc_names) > 1 else ""
    detail_parts = [p for p in [
        act or None,
        statut or None,
        f"réf {it.get('reference_id')}" if it.get("reference_id") else None,
        f"autres zones: {zones}" if zones else None,
        f"projet: {it.get('v2/location-ou-achat/votre-projet/radio')}" if it.get("v2/location-ou-achat/votre-projet/radio") else None,
    ] if p]
    return {
        "id_annonce": it.get("prospection_id") or it.get("id"),
        "ville": ville,
        "code_postal": None,
        "surface_min": smin,
        "surface_max": smax,
        "budget_max_mensuel": loyer_max(it),
        "activite_detaillee": " — ".join(detail_parts)[:500],
        "besoin_extraction": bool(it.get("v2/surface-et-criteres-techniques/mes-criteres-techniques/extraction-presente-ou-possible")),
        "url_contact": None,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--push", action="store_true", help="Pousse vers l'API ProFoods")
    parser.add_argument("--all-activities", action="store_true", help="Désactive le filtre food")
    args = parser.parse_args()

    if not EMAIL or not PASSWORD:
        sys.exit("UNEMPLACEMENT_EMAIL / UNEMPLACEMENT_PASSWORD manquants")

    token = get_id_token()
    print("[OK] Authentification Firebase")

    all_items, seen_ids = [], set()
    page, total = 0, None
    while True:
        data = fetch_page(token, page)
        items = data[0] if data and isinstance(data[0], list) else []
        if total is None and len(data) > 2 and isinstance(data[2], int):
            total = data[2]
            print(f"[INFO] {total} recherches annoncées pour {STATE}")
        new = [it for it in items if it.get("prospection_id") not in seen_ids]
        for it in new:
            seen_ids.add(it.get("prospection_id"))
        all_items.extend(new)
        print(f"  page {page}: {len(items)} items ({len(all_items)} cumulés)")
        if not items or (total is not None and len(all_items) >= total):
            break
        page += 1
        time.sleep(0.4)

    out_raw = "data/outputs/unemplacement_recherches_idf_raw.json"
    os.makedirs(os.path.dirname(out_raw), exist_ok=True)
    with open(out_raw, "w") as f:
        json.dump(all_items, f, ensure_ascii=False)
    print(f"[OK] {len(all_items)} recherches brutes sauvegardées -> {out_raw}")

    demandes, skipped = [], 0
    for it in all_items:
        act = activity_label(it)
        if not args.all_activities and act and not FOOD_KEYWORDS.search(act):
            skipped += 1
            continue
        if not args.all_activities and not act:
            skipped += 1
            continue
        d = map_demande(it)
        if d["id_annonce"]:
            demandes.append(d)
    print(f"[OK] {len(demandes)} demandes food conservées, {skipped} hors-scope écartées")

    out_mapped = "data/outputs/unemplacement_demandes_profoods.json"
    with open(out_mapped, "w") as f:
        json.dump(demandes, f, ensure_ascii=False, indent=1)
    print(f"[OK] Demandes mappées -> {out_mapped}")

    if args.push:
        inserted = 0
        for i in range(0, len(demandes), 50):
            batch = demandes[i:i + 50]
            r = requests.post(PUSH_URL, json={"demandes": batch}, timeout=60)
            if not r.ok:
                print(f"[ERR] batch {i}: {r.status_code} {r.text[:300]}")
                break
            inserted += r.json().get("inserted_demandes", 0)
            print(f"  batch {i}-{i + len(batch)}: OK ({inserted} insérées/maj)")
            time.sleep(0.3)
        print(f"[DONE] {inserted} demandes poussées vers {PUSH_URL}")


if __name__ == "__main__":
    main()
