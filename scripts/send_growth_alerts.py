#!/usr/bin/env python3
"""
Send weekly email alerts with top growth opportunities.
Uses growth_velocity_score computed by recalc_growth_score.py, based on
real signals: CA growth, relative site-opening velocity, Google Trends
momentum, and Google reviews/traction proxy.
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "prokitchens-app"))
os.environ.setdefault("PROKITCHENS_APP_DIR", os.path.join(os.path.dirname(__file__), "..", "prokitchens-app"))
from prokitchens_env import load_env
load_env()

SUPABASE_URL = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_API_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
RESEND_KEY = os.environ.get("RESEND_API_KEY")
EMAIL_TO = os.environ.get("NOTIFICATION_EMAIL_TO")

if not all([SUPABASE_URL, SUPABASE_KEY, RESEND_KEY, EMAIL_TO]):
    missing = [n for n, v in [("SUPABASE_URL", SUPABASE_URL), ("SUPABASE_KEY", SUPABASE_KEY),
                               ("RESEND_KEY", RESEND_KEY), ("EMAIL_TO", EMAIL_TO)] if not v]
    print(f"❌ Missing credentials: {', '.join(missing)}")
    sys.exit(1)

import requests

def get_top_growth_leads():
    """Get top 20 growth leads from the top_growth_leads view"""
    headers = {
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "apikey": SUPABASE_KEY
    }

    response = requests.get(
        f"{SUPABASE_URL}/rest/v1/top_growth_leads?"
        f"select=*&"
        f"order=growth_velocity_score.desc&"
        f"limit=20",
        headers=headers
    )

    if response.status_code == 200:
        return response.json()
    print(f"⚠️ Could not fetch top_growth_leads: {response.status_code} {response.text[:200]}")
    return []

def send_email(leads):
    """Send alert email via Resend"""
    if not leads:
        print("No high-growth leads to alert")
        return

    rows = ""
    for lead in leads[:20]:
        category = lead.get('growth_category', 'stable')
        score = lead.get('growth_velocity_score', 0) or 0
        sites_ouverts = lead.get('sites_ouverts_12m', 0) or 0
        croissance_ca = lead.get('croissance_ca')
        ca_display = f"+{croissance_ca:.0f}%" if croissance_ca else "N/A"

        rows += f"""
        <tr>
            <td style="padding: 10px; border-bottom: 1px solid #eee;">
                <strong>{lead['nom']}</strong>
                <br/><small>{lead.get('ville', 'N/A')} • {lead.get('region', 'N/A')}</small>
            </td>
            <td style="padding: 10px; border-bottom: 1px solid #eee; text-align: center;">
                <span style="background: {'#10b981' if score > 0.8 else '#3b82f6' if score > 0.5 else '#f59e0b'};
                            color: white; padding: 5px 10px; border-radius: 4px; font-weight: bold;">
                    {category.replace('-', ' ').title()}
                </span>
            </td>
            <td style="padding: 10px; border-bottom: 1px solid #eee; text-align: center;">
                {score:.0%}
            </td>
            <td style="padding: 10px; border-bottom: 1px solid #eee; text-align: center;">
                {ca_display}
            </td>
            <td style="padding: 10px; border-bottom: 1px solid #eee; text-align: center;">
                {sites_ouverts} nouveau(x) site(s) / 12m
            </td>
        </tr>
        """

    html = f"""
    <html>
        <head>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #333; }}
                .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
                table {{ width: 100%; border-collapse: collapse; }}
                th {{ background: #f3f4f6; padding: 12px; text-align: left; font-weight: 600; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2>🚀 ProKitchens — Rapport de croissance hebdomadaire</h2>
                <p>Top 20 opportunités QSR en forte croissance (y compris les petites structures en hyperscale)</p>

                <table>
                    <thead>
                        <tr>
                            <th>Restaurant</th>
                            <th>Catégorie</th>
                            <th>Score croissance</th>
                            <th>Croissance CA</th>
                            <th>Ouvertures récentes</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows}
                    </tbody>
                </table>

                <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
                <p style="color: #666; font-size: 12px;">
                    <strong>Score de croissance</strong> : combine croissance du CA, vitesse d'ouverture de nouveaux sites
                    (relative à la taille — un passage de 1 à 2 sites compte autant qu'un passage de 50 à 100),
                    tendances Google régionales, et traction (avis Google).
                    <br/>
                    <strong>Hyper-growth</strong> : &gt; 80% | <strong>Strong growth</strong> : &gt; 50% | <strong>Growth</strong> : &gt; 30%
                </p>
            </div>
        </body>
    </html>
    """

    response = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {RESEND_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "from": "ProKitchens <onboarding@resend.dev>",
            "to": EMAIL_TO,
            "subject": f"🚀 ProKitchens Growth Report — {datetime.now().strftime('%Y-%m-%d')}",
            "html": html
        }
    )

    if response.status_code == 200:
        print(f"✅ Email sent to {EMAIL_TO}")
    else:
        print(f"❌ Failed to send email: {response.status_code}")
        print(response.text)

if __name__ == "__main__":
    leads = get_top_growth_leads()
    send_email(leads)
