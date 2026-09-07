#!/usr/bin/env python3
"""
Growth Velocity Scoring for ProKitchens
Calculates composite score based on RELATIVE growth velocity (not absolute size),
so small/emerging QSRs with strong momentum surface even with a low absolute score.

Signals used (all reliably populated by existing pipelines — no fragile scraping):
- CA growth (croissance_ca, from Sirene/INPI enrichment)
- New site openings velocity (sites_ouverts_12m relative to total sites — a 1->2 site
  QSR scores higher on this axis than a 50->51 site chain, by design)
- Google Trends regional momentum (google_trend_score)
- Original score (proxy for Google reviews/traction already enriched)

NOTE: An earlier version depended on LinkedIn follower/hiring data. Scrapped after
verifying LinkedIn blocks all unauthenticated/automated access (authwall + bot
detection) even on public company pages — it would have run hourly and silently
produced zero real data forever. Removed to avoid wasting CI minutes on a dead
scraper and to keep the score honest.
"""

import os
import sys
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Tuple

import requests

SUPABASE_URL = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_API_KEY:
    print("❌ Supabase credentials missing")
    sys.exit(1)

HEADERS = {
    "apikey": SUPABASE_API_KEY,
    "Authorization": f"Bearer {SUPABASE_API_KEY}",
    "Content-Type": "application/json",
}

BATCH_WRITE_SIZE = 200
REQUEST_DELAY = 0.05
LOG_FILE = "/zpool/one/maxime.debaugnies/logs/recalc_growth_score.log"


def log(msg: str):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def fetch_all_leads() -> List[Dict[str, Any]]:
    leads: List[Dict[str, Any]] = []
    offset = 0
    page_size = 1000
    while True:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/leads",
            headers=HEADERS,
            params={
                "select": "id,nom,ville,score,croissance_ca,sites_ouverts_12m,nb_etablissements,google_trend_score",
                "order": "score.desc",
                "limit": page_size,
                "offset": offset,
            },
            timeout=60,
        )
        if resp.status_code != 200:
            log(f"❌ Failed to fetch leads: {resp.status_code} {resp.text[:200]}")
            break
        batch = resp.json()
        if not batch:
            break
        leads.extend(batch)
        offset += len(batch)
        if len(batch) < page_size:
            break
    return leads


def calculate_growth_velocity(lead: Dict[str, Any]) -> Tuple[float, Dict[str, float]]:
    """
    Composite growth velocity score (0.0 to 1.0):
    - CA growth: 30%
    - Site opening velocity (relative, favors small QSRs): 30%
    - Google Trends regional momentum: 20%
    - Original score (proxy for reviews/traction): 20%
    """
    scores = {}

    ca_growth = lead.get("croissance_ca") or 0
    scores["ca"] = min(ca_growth / 50, 1.0) if ca_growth > 0 else 0.0

    sites_ouverts = lead.get("sites_ouverts_12m") or 0
    nb_etablissements = lead.get("nb_etablissements") or 1
    sites_before = max(nb_etablissements - sites_ouverts, 1)
    scores["sites"] = min(sites_ouverts / sites_before, 1.0) if sites_ouverts > 0 else 0.0

    scores["trend"] = float(lead.get("google_trend_score") or 0.0)

    original_score = lead.get("score") or 0
    scores["original"] = min(original_score / 100, 1.0)

    velocity_score = (
        scores["ca"] * 0.30
        + scores["sites"] * 0.30
        + scores["trend"] * 0.20
        + scores["original"] * 0.20
    )

    return round(min(velocity_score, 1.0), 3), scores


def update_one(lead: Dict[str, Any]) -> Tuple[int, int, float]:
    velocity_score, components = calculate_growth_velocity(lead)
    payload = {
        "growth_velocity_score": velocity_score,
        "growth_velocity_components": components,
        "growth_velocity_updated_at": datetime.utcnow().isoformat(),
        "alert_growth_momentum": velocity_score > 0.6,
    }
    try:
        resp = requests.patch(
            f"{SUPABASE_URL}/rest/v1/leads",
            headers=HEADERS,
            params={"id": f"eq.{lead['id']}"},
            json=payload,
            timeout=30,
        )
        if resp.status_code in (200, 204):
            return 1, 0, velocity_score
        log(f"Erreur update id={lead['id']}: HTTP {resp.status_code} {resp.text[:150]}")
        return 0, 1, velocity_score
    except Exception as e:
        log(f"Exception update id={lead['id']}: {e}")
        return 0, 1, velocity_score
    finally:
        time.sleep(REQUEST_DELAY)


def update_batch(leads: List[Dict[str, Any]]) -> Tuple[int, int, List[Tuple[str, str, float]]]:
    ok = 0
    ko = 0
    high_growth: List[Tuple[str, str, float]] = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(update_one, lead): lead for lead in leads}
        for future in as_completed(futures):
            lead = futures[future]
            o, k, score = future.result()
            ok += o
            ko += k
            if score > 0.6:
                high_growth.append((lead["nom"], lead.get("ville", ""), score))
    return ok, ko, high_growth


def main():
    log("=" * 60)
    log("Recalcul growth velocity score")
    log("=" * 60)

    leads = fetch_all_leads()
    log(f"{len(leads)} leads récupérés")

    total_ok = 0
    total_ko = 0
    all_high_growth: List[Tuple[str, str, float]] = []

    for i in range(0, len(leads), BATCH_WRITE_SIZE):
        batch = leads[i : i + BATCH_WRITE_SIZE]
        ok, ko, high_growth = update_batch(batch)
        total_ok += ok
        total_ko += ko
        all_high_growth.extend(high_growth)
        log(f"Batch {i // BATCH_WRITE_SIZE + 1}/{(len(leads) - 1) // BATCH_WRITE_SIZE + 1}: {ok} OK, {ko} KO (total OK {total_ok})")

    log(f"TERMINÉ: {total_ok} mis à jour, {total_ko} erreurs")

    if all_high_growth:
        all_high_growth.sort(key=lambda x: x[2], reverse=True)
        log("\nTOP 10 HYPER-GROWTH LEADS:")
        for nom, ville, score in all_high_growth[:10]:
            log(f"  {score:.3f} — {nom} ({ville})")


if __name__ == "__main__":
    main()
