#!/usr/bin/env python3
"""Spot-check des scores canonical sur un échantillon de leads."""
import os
import sys
from datetime import datetime

import prokitchens_env
prokitchens_env.load_env()

import requests

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY", "")

HEADERS = {
    "apikey": SUPABASE_API_KEY,
    "Authorization": f"Bearer {SUPABASE_API_KEY}",
    "Accept": "application/json",
}

SCORE_COLUMNS = [
    "score", "score_total", "score_ca", "score_sites", "score_croissance",
    "score_contact", "score_intention", "score_chaine",
]


def fetch_sample():
    params = {
        "select": f"id,siren,nom,nb_etablissements,chiffre_affaires,croissance_ca,telephone,site_web,email,nb_tenders,nb_tender_notices,is_chaine,derniere_ouverture,sites_ouverts_12m,{','.join(SCORE_COLUMNS)}",
        "order": "score_total.desc.nullslast",
        "limit": 10,
    }
    resp = requests.get(f"{SUPABASE_URL}/rest/v1/leads", headers=HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def recompute_expected(lead):
    from datetime import datetime, timedelta

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

    score_ca = 0
    if has_ca:
        if ca >= 5_000_000: score_ca = 30
        elif ca >= 2_000_000: score_ca = 25
        elif ca >= 1_000_000: score_ca = 20
        elif ca >= 500_000: score_ca = 15
        elif ca >= 100_000: score_ca = 10
        else: score_ca = 5

    score_sites_raw = 0
    if nb_etabs >= 10: score_sites_raw = 35
    elif nb_etabs >= 5: score_sites_raw = 30
    elif nb_etabs >= 3: score_sites_raw = 20
    elif nb_etabs >= 2: score_sites_raw = 12

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

    score_contact = 0
    if lead.get("telephone"): score_contact += 10
    if lead.get("site_web"): score_contact += 8
    if lead.get("email"): score_contact += 7

    score_intention = 0
    if has_ca_growth:
        if g >= 30: score_intention += 10
        elif g >= 15: score_intention += 7
        elif g >= 5: score_intention += 4
    if sites_ouverts >= 3: score_intention += 8
    elif sites_ouverts >= 1: score_intention += 4
    if (lead.get("nb_tenders") or 0) >= 1: score_intention += 5
    if (lead.get("nb_tender_notices") or 0) >= 1: score_intention += 2

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
        "score_total": score_total,
        "score_ca": score_ca,
        "score_sites": score_sites,
        "score_croissance": score_croissance,
        "score_contact": score_contact,
        "score_intention": score_intention,
        "score_chaine": score_chaine,
    }


def main():
    print(f"[{datetime.now()}] Spot-check des scores — top 10 leads")
    sample = fetch_sample()
    if not sample:
        print("Aucun lead trouvé.")
        return 1

    issues = []
    for lead in sample:
        expected = recompute_expected(lead)
        row = {k: lead.get(k) for k in SCORE_COLUMNS}
        mismatches = [k for k in expected if row.get(k) != expected[k]]
        status = "OK" if not mismatches else "MISMATCH"
        print(f"\n{lead.get('siren')} — {lead.get('nom')[:50]} — {status}")
        for k in SCORE_COLUMNS:
            exp = expected.get(k, "-")
            got = row.get(k, "-")
            marker = "  <--" if k in mismatches else ""
            print(f"  {k}: got={got} expected={exp}{marker}")
        if mismatches:
            issues.append(lead.get("siren"))

    print(f"\n[{datetime.now()}] Résultat: {len(sample) - len(issues)}/{len(sample)} leads cohérents")
    if issues:
        print(f"SIREN avec écarts: {', '.join(issues)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
