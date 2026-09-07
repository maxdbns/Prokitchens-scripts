#!/usr/bin/env python3
"""
Google Trends momentum detection for ProKitchens
Detects trending restaurant/food keywords by region to identify hyper-growth
opportunities. Uses pytrends (unofficial but stable API, verified working).
"""

import os
import sys
from datetime import datetime
from urllib.parse import quote

SUPABASE_URL = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_API_KEY:
    print("❌ Supabase credentials missing")
    sys.exit(1)

import requests
from pytrends.request import TrendReq

pytrends = TrendReq(hl='fr_FR', tz=60)

KEYWORDS = [
    "restaurant",
    "dark kitchen",
    "cloud kitchen",
    "fast food",
    "ghost kitchen",
]  # Google Trends caps comparisons at 5 keywords per request

def headers():
    return {
        "Authorization": f"Bearer {SUPABASE_API_KEY}",
        "apikey": SUPABASE_API_KEY,
        "Content-Type": "application/json",
    }

def get_regions():
    """Fetch all distinct regions across the full leads table (paginated —
    PostgREST has no DISTINCT, and a single unpaginated page only reflects
    whatever slice happens to sort first, missing every other region)."""
    regions = set()
    offset = 0
    page_size = 5000
    while True:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/leads",
            headers=headers(),
            params={
                "select": "region",
                "region": "not.is.null",
                "limit": page_size,
                "offset": offset,
            },
        )
        if resp.status_code != 200:
            print(f"❌ Failed to fetch regions: {resp.status_code} {resp.text[:200]}")
            break
        batch = resp.json()
        if not batch:
            break
        regions.update(row["region"] for row in batch if row.get("region"))
        offset += len(batch)
        if len(batch) < page_size:
            break
    return sorted(regions)

def get_trending_keywords():
    """Get trending food/restaurant keywords nationally (FR).
    Kept national (not per-region) because Google Trends' regional breakdown
    for niche keywords is too sparse to be reliable at department/region level."""
    try:
        pytrends.build_payload(KEYWORDS, timeframe='now 7-d', geo='FR')
        interest = pytrends.interest_over_time()

        if interest.empty:
            return []

        trend_data = {}
        for keyword in KEYWORDS:
            if keyword in interest.columns:
                values = interest[keyword].values
                if values[-1] > 0:
                    momentum = (values[-1] - values[0]) / max(values[0], 1)
                    if momentum > 0.1:
                        trend_data[keyword] = float(momentum)

        return sorted(trend_data.items(), key=lambda x: x[1], reverse=True)[:3]
    except Exception as e:
        print(f"⚠️ Trends error: {e}")
        return []

def enrich_trends():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting Google Trends enrichment\n")

    trending = get_trending_keywords()

    if not trending:
        print("No trends detected — leaving existing scores untouched")
        return

    trend_score = min(0.5 + sum(momentum for _, momentum in trending) * 0.1, 1.0)
    keywords = [kw for kw, _ in trending]
    print(f"National trend score: {trend_score:.2f} ({', '.join(keywords)})\n")

    regions = get_regions()
    print(f"Applying to {len(regions)} regions (one bulk update per region)\n")

    total_updated = 0
    for region in regions:
        try:
            resp = requests.patch(
                f"{SUPABASE_URL}/rest/v1/leads?region=eq.{quote(region)}",
                headers={**headers(), "Prefer": "count=exact"},
                json={
                    "google_trend_score": trend_score,
                    "google_trend_keywords": keywords,
                    "google_trend_last_checked": datetime.utcnow().isoformat(),
                },
            )
            if resp.status_code == 204:
                count = resp.headers.get("Content-Range", "?/?").split("/")[-1]
                print(f"  ✅ {region}: {count} leads updated")
                total_updated += 1
            else:
                print(f"  ⚠️ {region}: {resp.status_code} {resp.text[:150]}")
        except Exception as e:
            print(f"  ⚠️ {region}: update error {e}")

    print(f"\n✅ Updated leads across {total_updated}/{len(regions)} regions")

if __name__ == "__main__":
    enrich_trends()
