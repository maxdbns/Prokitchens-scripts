#!/usr/bin/env python3
"""Recalcule les scores canonical pour tous les leads via l'API REST Supabase.

Utilisé quand on ne peut pas exécuter sql/recalc_scores.sql directement
(par exemple pas d'accès psql / SQL Editor).
"""
import os
import sys
import time
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple

import prokitchens_env
prokitchens_env.load_env()

import requests

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY", "")
if not SUPABASE_URL or not SUPABASE_API_KEY:
    print("SUPABASE_URL ou SUPABASE_API_KEY manquant")
    sys.exit(1)

HEADERS = {
    "apikey": SUPABASE_API_KEY,
    "Authorization": f"Bearer {SUPABASE_API_KEY}",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}
READ_HEADERS = {
    "apikey": SUPABASE_API_KEY,
    "Authorization": f"Bearer {SUPABASE_API_KEY}",
    "Accept": "application/json",
}

SELECT_COLUMNS = [
    "id", "siren", "nom", "nb_etablissements", "chiffre_affaires", "croissance_ca",
    "telephone", "site_web", "email", "nb_tenders", "nb_tender_notices", "is_chaine",
    "derniere_ouverture", "sites_ouverts_12m", "created_at",
]

BATCH_READ_SIZE = 1000
BATCH_WRITE_SIZE = 500
REQUEST_DELAY = 0.1
LOG_FILE = "/zpool/one/maxime.debaugnies/logs/recalc_scores_api.log"


def log(msg: str):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def compute_score(lead: Dict[str, Any]) -> Dict[str, int]:
    ca = lead.get("chiffre_affaires")
    has_ca = ca is not None and ca > 0
    g = lead.get("croissance_ca")
    has_ca_growth = g is not None
    nb_etabs = lead.get("nb_etablissements") or 1
    sites_ouverts = lead.get("sites_ouverts_12m") or 0
    derniere_ouverture = lead.get("derniere_ouverture")

    within_6_months = False
    within_12_months = False
    if derniere_ouverture:
        try:
            d = datetime.fromisoformat(str(derniere_ouverture).replace("Z", "+00:00"))
            now = datetime.now(d.tzinfo) if d.tzinfo else datetime.now()
            within_6_months = d >= now - timedelta(days=180)
            within_12_months = d >= now - timedelta(days=365)
        except Exception:
            pass

    # Axe CA (max 30)
    score_ca = 0
    if has_ca:
        if ca >= 5_000_000: score_ca = 30
        elif ca >= 2_000_000: score_ca = 25
        elif ca >= 1_000_000: score_ca = 20
        elif ca >= 500_000: score_ca = 15
        elif ca >= 100_000: score_ca = 10
        else: score_ca = 5

    # Axe Sites (max 35, redistribué à 60 si CA absent)
    score_sites_raw = 0
    if nb_etabs >= 10: score_sites_raw = 35
    elif nb_etabs >= 5: score_sites_raw = 30
    elif nb_etabs >= 3: score_sites_raw = 20
    elif nb_etabs >= 2: score_sites_raw = 12

    # Axe Croissance (max 30)
    score_ca_growth = 0
    if has_ca_growth:
        if g >= 30: score_ca_growth = 15
        elif g >= 15: score_ca_growth = 12
        elif g >= 5: score_ca_growth = 8
        elif g >= 0: score_ca_growth = 4

    score_ouvertures = 0
    if sites_ouverts >= 3: score_ouvertures = 10
    elif sites_ouverts >= 2: score_ouvertures = 6
    elif sites_ouverts >= 1: score_ouvertures = 3 if within_6_months else 0

    score_combo = 0
    if derniere_ouverture:
        if nb_etabs >= 3 and within_6_months: score_combo = 5
        elif nb_etabs >= 2 and within_12_months: score_combo = 2

    score_croissance = score_ca_growth + score_ouvertures + score_combo

    if not has_ca:
        score_sites = round(score_sites_raw / 35 * 60)
    else:
        score_sites = score_sites_raw

    # Axe Contact (max 25)
    score_contact = 0
    if lead.get("telephone"): score_contact += 10
    if lead.get("site_web"): score_contact += 8
    if lead.get("email"): score_contact += 7

    # Axe Intention (max 25)
    score_intention = 0
    if has_ca_growth:
        if g >= 30: score_intention += 10
        elif g >= 15: score_intention += 7
        elif g >= 5: score_intention += 4
    if sites_ouverts >= 3: score_intention += 8
    elif sites_ouverts >= 1: score_intention += 4
    if (lead.get("nb_tenders") or 0) >= 1: score_intention += 5
    if (lead.get("nb_tender_notices") or 0) >= 1: score_intention += 2

    # Axe Chaîne / Franchise (max 20)
    score_chaine = 0
    if nb_etabs >= 10: score_chaine = 15
    elif nb_etabs >= 5: score_chaine = 12
    elif nb_etabs >= 3: score_chaine = 8
    elif nb_etabs >= 2: score_chaine = 4
    if lead.get("is_chaine"): score_chaine += 5

    score_total = round(
        (
            score_ca / 30.0 * 0.30
            + score_sites / 35.0 * 0.25
            + score_croissance / 30.0 * 0.20
            + score_contact / 25.0 * 0.10
            + score_intention / 25.0 * 0.10
            + score_chaine / 20.0 * 0.05
        ) * 100
    )
    return {
        "score": score_total,
        "score_total": score_total,
        "score_ca": score_ca,
        "score_sites": score_sites,
        "score_croissance": score_croissance,
        "score_contact": score_contact,
        "score_intention": score_intention,
        "score_chaine": score_chaine,
    }


def fetch_all_leads(limit: int = None) -> List[Dict[str, Any]]:
    leads = []
    offset = 0
    while True:
        params = {
            "select": ",".join(SELECT_COLUMNS),
            "limit": BATCH_READ_SIZE,
            "offset": offset,
            "order": "id.asc",
        }
        resp = requests.get(f"{SUPABASE_URL}/rest/v1/leads", headers=READ_HEADERS, params=params, timeout=60)
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        leads.extend(batch)
        offset += len(batch)
        if limit and len(leads) >= limit:
            return leads[:limit]
        log(f"Lu {len(leads)} leads...")
    return leads


PATCH_HEADERS = {
    "apikey": SUPABASE_API_KEY,
    "Authorization": f"Bearer {SUPABASE_API_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}


def update_one(lead: Dict[str, Any]) -> Tuple[int, int]:
    scores = compute_score(lead)
    payload = {
        "score": scores["score"],
        "score_total": scores["score_total"],
        "score_ca": scores["score_ca"],
        "score_sites": scores["score_sites"],
        "score_croissance": scores["score_croissance"],
        "score_contact": scores["score_contact"],
        "score_intention": scores["score_intention"],
        "score_chaine": scores["score_chaine"],
    }
    try:
        resp = requests.patch(
            f"{SUPABASE_URL}/rest/v1/leads",
            headers=PATCH_HEADERS,
            params={"id": f"eq.{lead['id']}"},
            json=payload,
            timeout=30,
        )
        if resp.status_code in (200, 204):
            return 1, 0
        else:
            log(f"Erreur update id={lead['id']} siren={lead['siren']}: HTTP {resp.status_code} {resp.text[:200]}")
            return 0, 1
    except Exception as e:
        log(f"Exception update id={lead['id']} siren={lead['siren']}: {e}")
        return 0, 1
    finally:
        time.sleep(REQUEST_DELAY)


def update_batch(leads: List[Dict[str, Any]]) -> Tuple[int, int]:
    ok = 0
    ko = 0
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(update_one, lead): lead for lead in leads}
        for future in as_completed(futures):
            o, k = future.result()
            ok += o
            ko += k
    return ok, ko


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Nombre max de leads à traiter (test)")
    parser.add_argument("--dry-run", action="store_true", help="Calculer sans écrire")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    log(f"Démarrage recalc_scores_api (limit={args.limit}, dry_run={args.dry_run})")

    leads = fetch_all_leads(limit=args.limit)
    log(f"Total leads lus : {len(leads)}")

    if args.dry_run:
        for lead in leads[:5]:
            scores = compute_score(lead)
            log(f"{lead['siren']} {lead['nom'][:30]}: {scores}")
        log("Dry-run terminé.")
        return 0

    total_ok = 0
    total_ko = 0
    for i in range(0, len(leads), BATCH_WRITE_SIZE):
        batch = leads[i:i + BATCH_WRITE_SIZE]
        ok, ko = update_batch(batch)
        total_ok += ok
        total_ko += ko
        log(f"Batch {i//BATCH_WRITE_SIZE + 1}/{(len(leads) - 1)//BATCH_WRITE_SIZE + 1}: {ok} OK, {ko} KO (total OK {total_ok})")

    log(f"Terminé : {total_ok} OK, {total_ko} KO sur {len(leads)} leads")
    return 0 if total_ko == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
