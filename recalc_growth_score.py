#!/usr/bin/env python3
"""
Growth Velocity Scoring for ProKitchens
Calculates composite score based on:
- CA growth trajectory (last 12 months)
- Employee growth (hiring momentum)
- LinkedIn follower growth
- Google Trends momentum
- Google review velocity
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "prokitchens-app"))
from prokitchens_env import load_env
load_env()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_API_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ Supabase credentials missing")
    sys.exit(1)

import requests
import json

def calculate_growth_velocity(lead):
    """
    Calculate composite growth velocity score (0.0 to 1.0)
    Weights:
    - CA growth: 30%
    - LinkedIn hires: 20%
    - LinkedIn follower growth: 20%
    - Google Trends: 15%
    - Original score (proxy for avis Google): 15%
    """

    scores = {}

    # 1. CA Growth (30%)
    # Simple heuristic: croissance_ca > 0 means growth
    ca_growth = lead.get('croissance_ca') or 0
    if ca_growth > 0:
        scores['ca'] = min(abs(ca_growth) / 100, 1.0)  # 20% growth -> 0.2
    else:
        scores['ca'] = 0.0

    # 2. LinkedIn Hires (20%)
    # Hires indicate growth velocity
    hires_3m = lead.get('linkedin_hires_3m') or 0
    if hires_3m > 0:
        # 5+ hires in 3 months = max score
        scores['hires'] = min(hires_3m / 5, 1.0)
    else:
        scores['hires'] = 0.0

    # 3. LinkedIn Follower Growth (20%)
    # follower_30d_change tracks momentum
    followers_change = lead.get('linkedin_followers_30d_change') or 0
    total_followers = lead.get('linkedin_followers') or 1
    if total_followers > 0:
        growth_rate = followers_change / total_followers if total_followers > 0 else 0
        scores['followers'] = min(max(growth_rate, 0), 1.0)
    else:
        scores['followers'] = 0.0

    # 4. Google Trends (15%)
    google_trend = lead.get('google_trend_score') or 0.0
    scores['trend'] = float(google_trend)

    # 5. Original Score Proxy (15%)
    # Lead's original score is proxy for reviews/traction
    original_score = lead.get('score') or 0
    scores['original'] = min(original_score / 100, 1.0)

    # Weighted average
    velocity_score = (
        scores['ca'] * 0.30 +
        scores['hires'] * 0.20 +
        scores['followers'] * 0.20 +
        scores['trend'] * 0.15 +
        scores['original'] * 0.15
    )

    return round(min(velocity_score, 1.0), 3), scores

def recalc_all_scores():
    """Recalculate growth velocity for all leads"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Recalculating growth velocity scores\n")

    headers = {
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "apikey": SUPABASE_KEY
    }

    # Fetch all leads
    response = requests.get(
        f"{SUPABASE_URL}/rest/v1/leads?"
        f"select=id,nom,ville,score,croissance_ca,linkedin_followers,"
        f"linkedin_followers_30d_change,linkedin_hires_3m,google_trend_score&"
        f"order=score.desc&"
        f"limit=10000",
        headers=headers
    )

    if response.status_code != 200:
        print(f"❌ Failed to fetch leads: {response.status_code}")
        return

    leads = response.json()
    print(f"Processing {len(leads)} leads...\n")

    # Calculate and update
    updated = 0
    high_growth = []

    for i, lead in enumerate(leads, 1):
        velocity_score, components = calculate_growth_velocity(lead)

        # Update lead
        update_response = requests.patch(
            f"{SUPABASE_URL}/rest/v1/leads?id=eq.{lead['id']}",
            headers=headers,
            json={
                "growth_velocity_score": velocity_score,
                "growth_velocity_components": components,
                "growth_velocity_updated_at": datetime.utcnow().isoformat(),
                "alert_growth_momentum": velocity_score > 0.6  # Flag high growth
            }
        )

        if update_response.status_code == 204:
            updated += 1
            if velocity_score > 0.6:
                high_growth.append((lead['nom'], lead['ville'], velocity_score))

        if i % 100 == 0:
            print(f"  [{i}/{len(leads)}] {updated} updated")

    print(f"\n✅ Updated {updated} leads")

    # Show top 10 high-growth leads
    if high_growth:
        high_growth.sort(key=lambda x: x[2], reverse=True)
        print(f"\n🚀 TOP 10 HYPER-GROWTH LEADS:\n")
        for nom, ville, score in high_growth[:10]:
            print(f"  {score:.3f} — {nom} ({ville})")

if __name__ == "__main__":
    recalc_all_scores()
