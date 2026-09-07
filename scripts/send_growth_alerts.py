#!/usr/bin/env python3
"""
Send weekly email alerts with top growth opportunities
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../prokitchens-app"))
from prokitchens_env import load_env
load_env()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_API_KEY")
RESEND_KEY = os.environ.get("RESEND_API_KEY")
EMAIL_TO = os.environ.get("NOTIFICATION_EMAIL_TO")

if not all([SUPABASE_URL, SUPABASE_KEY, RESEND_KEY, EMAIL_TO]):
    print("❌ Missing credentials")
    sys.exit(1)

import requests

def get_top_growth_leads():
    """Get top 20 growth leads from this week"""
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
    return []

def send_email(leads):
    """Send alert email via Resend"""
    if not leads:
        print("No high-growth leads to alert")
        return

    # Build HTML table
    rows = ""
    for lead in leads[:20]:
        category = lead.get('growth_category', 'stable')
        score = lead.get('growth_velocity_score', 0)
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
                {score:.2%}
            </td>
            <td style="padding: 10px; border-bottom: 1px solid #eee; text-align: center;">
                {lead.get('linkedin_followers', 0):,} followers
            </td>
            <td style="padding: 10px; border-bottom: 1px solid #eee; text-align: center;">
                {lead.get('linkedin_hires_3m', 0)} hires
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
                <h2>🚀 ProKitchens Weekly Growth Report</h2>
                <p>Top 20 hyper-scale QSR opportunities detected this week</p>

                <table>
                    <thead>
                        <tr>
                            <th>Restaurant</th>
                            <th>Category</th>
                            <th>Growth Score</th>
                            <th>LinkedIn Followers</th>
                            <th>Recent Hires (3m)</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows}
                    </tbody>
                </table>

                <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
                <p style="color: #666; font-size: 12px;">
                    <strong>Growth Score</strong>: Composite metric of CA growth, LinkedIn hiring, follower growth, Google Trends momentum
                    <br/>
                    <strong>Hyper-growth</strong>: > 80% | <strong>Strong growth</strong>: > 50% | <strong>Growth</strong>: > 30%
                </p>
            </div>
        </body>
    </html>
    """

    # Send via Resend
    response = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {RESEND_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "from": "ProKitchens <noreply@prokitchens.dev>",
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
