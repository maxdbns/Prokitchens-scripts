#!/usr/bin/env python3
"""
Google Trends momentum detection for ProKitchens
Detects trending keywords by region to identify hyper-growth opportunities
Uses pytrends (unofficial but stable API)
"""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "prokitchens-app"))
from prokitchens_env import load_env
load_env()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_API_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ Supabase credentials missing")
    sys.exit(1)

import requests
from pytrends.request import TrendReq

# Initialize pytrends
pytrends = TrendReq(hl='fr_FR', tz=60)

# French regions
REGIONS = [
    "Ile-de-France",
    "Auvergne-Rhône-Alpes",
    "Provence-Alpes-Côte d'Azur",
    "Hauts-de-France",
    "Occitanie",
    "Nouvelle-Aquitaine",
    "Grand Est",
    "Bretagne",
    "Pays de la Loire",
    "Normandie",
    "Centre-Val de Loire",
    "Corse"
]

def get_trending_keywords(region):
    """Get trending food/restaurant keywords for a region"""
    try:
        keywords = [
            "restaurant",
            "cuisine",
            "QSR",
            "food delivery",
            "dark kitchen",
            "cloud kitchen",
            "fast food",
            "micro-restaurant",
            "pop-up restaurant",
            "ghost kitchen"
        ]

        # Check which keywords are trending in this region
        pytrends.build_payload(keywords, timeframe='now 7-d', geo='FR')
        interest_over_time = pytrends.interest_over_time()

        # Calculate momentum (trend over last 7 days)
        if not interest_over_time.empty:
            trend_data = {}
            for keyword in keywords:
                if keyword in interest_over_time.columns:
                    values = interest_over_time[keyword].values
                    # Calculate simple momentum: (latest - oldest) / oldest
                    if values[-1] > 0:
                        momentum = (values[-1] - values[0]) / max(values[0], 1)
                        if momentum > 0.1:  # Only keywords growing > 10%
                            trend_data[keyword] = float(momentum)

            return sorted(trend_data.items(), key=lambda x: x[1], reverse=True)[:3]
        return []
    except Exception as e:
        print(f"⚠️ Trends error for {region}: {e}")
        return []

def enrich_trends():
    """Update all leads with Google Trends momentum scores"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting Google Trends enrichment\n")

    headers = {
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "apikey": SUPABASE_KEY
    }

    # Get all leads by region
    response = requests.get(
        f"{SUPABASE_URL}/rest/v1/leads?select=id,region,score&limit=10000",
        headers=headers
    )

    if response.status_code != 200:
        print(f"❌ Failed to fetch leads: {response.status_code}")
        return

    leads = response.json()
    leads_by_region = {}

    for lead in leads:
        region = lead.get('region') or 'Unknown'
        if region not in leads_by_region:
            leads_by_region[region] = []
        leads_by_region[region].append(lead)

    print(f"Processing {len(leads)} leads across {len(leads_by_region)} regions\n")

    total_updated = 0

    for region, region_leads in leads_by_region.items():
        print(f"📍 {region}...", end=" ", flush=True)

        # Get trending keywords for this region
        trending = get_trending_keywords(region)

        if trending:
            # Calculate trend score (0.0 to 1.0)
            trend_score = min(0.5 + sum(momentum for _, momentum in trending) * 0.1, 1.0)
            keywords = [kw for kw, _ in trending]

            print(f"Trend score: {trend_score:.2f} ({', '.join(keywords[:2])})")

            # Update all leads in this region
            for lead in region_leads:
                try:
                    update_response = requests.patch(
                        f"{SUPABASE_URL}/rest/v1/leads?id=eq.{lead['id']}",
                        headers=headers,
                        json={
                            "google_trend_score": trend_score,
                            "google_trend_keywords": keywords,
                            "google_trend_last_checked": datetime.utcnow().isoformat()
                        }
                    )
                    if update_response.status_code == 204:
                        total_updated += 1
                except Exception as e:
                    print(f"⚠️ Update error: {e}")
        else:
            print("No trends detected")

    print(f"\n✅ Updated {total_updated} leads with Google Trends data")

if __name__ == "__main__":
    enrich_trends()
