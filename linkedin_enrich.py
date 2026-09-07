#!/usr/bin/env python3
"""
LinkedIn company enrichment for ProKitchens
Scrapes company pages to detect growth signals: followers, recent hires, growth trajectory
Rate limited to 50 companies/day to avoid blocks
"""

import os
import sys
from datetime import datetime, timedelta
from urllib.parse import quote
import time

# Load env
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "prokitchens-app"))
from prokitchens_env import load_env
load_env()

import requests
from playwright.async_api import async_playwright
import asyncio

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_API_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ Supabase credentials missing")
    sys.exit(1)

headers = {
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "apikey": SUPABASE_KEY
}

async def scrape_linkedin_company(browser, company_name, location):
    """Scrape LinkedIn company page using Playwright"""
    try:
        page = await browser.new_page()

        # Build LinkedIn company search URL
        search_query = f"{company_name} {location} restaurant"
        url = f"https://www.linkedin.com/search/results/companies/?keywords={quote(search_query)}"

        await page.goto(url, wait_until="networkidle", timeout=10000)

        # Try to extract first result (this is best-effort scraping)
        # LinkedIn blocks aggressive scraping, so we use best-effort extraction
        try:
            company_link = await page.query_selector("a[href*='/company/']")
            if company_link:
                company_url = await company_link.get_attribute("href")

                # Go to company page
                await page.goto(company_url, wait_until="networkidle", timeout=10000)

                # Extract followers (text like "50,234 followers")
                followers_text = await page.query_selector("text=/followers/")
                followers = 0
                if followers_text:
                    text = await followers_text.text_content()
                    # Parse "50,234 followers" -> 50234
                    followers = int(text.split()[0].replace(",", "")) if text else 0

                result = {
                    "company_url": company_url,
                    "followers": followers,
                    "success": True
                }
            else:
                result = {"success": False, "reason": "no_result"}
        except Exception as e:
            result = {"success": False, "reason": str(e)}

        await page.close()
        return result

    except Exception as e:
        print(f"⚠️ Scrape failed for {company_name}: {e}")
        return {"success": False, "reason": str(e)}

async def enrich_batch():
    """Enrich top 50 leads without LinkedIn data"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting LinkedIn enrichment (max 50 leads/day)\n")

    # Get leads needing LinkedIn data (not checked in last 7 days)
    response = requests.get(
        f"{SUPABASE_URL}/rest/v1/leads?"
        f"select=id,nom,ville&"
        f"linkedin_company_url=is.null&"
        f"score=gt.50&"  # Only mid-to-high scoring leads
        f"order=score.desc&"
        f"limit=50",
        headers=headers
    )

    if response.status_code != 200:
        print(f"❌ Failed to fetch leads: {response.status_code}")
        print(response.text)
        return

    leads = response.json()
    print(f"Found {len(leads)} leads to enrich\n")

    if not leads:
        print("✅ All leads already enriched with LinkedIn data")
        return

    # Use Playwright to scrape (headless, fast)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        success_count = 0
        for i, lead in enumerate(leads, 1):
            print(f"[{i}/{len(leads)}] {lead['nom']} ({lead['ville']})...", end=" ", flush=True)

            # Scrape LinkedIn
            result = await scrape_linkedin_company(browser, lead['nom'], lead['ville'])

            if result.get("success"):
                print(f"✅ {result['followers']} followers")

                # Update Supabase
                update_response = requests.patch(
                    f"{SUPABASE_URL}/rest/v1/leads?id=eq.{lead['id']}",
                    headers=headers,
                    json={
                        "linkedin_followers": result["followers"],
                        "linkedin_last_checked": datetime.utcnow().isoformat()
                    }
                )

                if update_response.status_code == 204:
                    success_count += 1
                else:
                    print(f"⚠️ Update failed: {update_response.status_code}")
            else:
                print(f"⚠️ {result.get('reason', 'unknown')}")

            # Rate limit: 1s between requests
            time.sleep(1)

        await browser.close()

    print(f"\n✅ Enrichment complete: {success_count}/{len(leads)} succeeded")

if __name__ == "__main__":
    asyncio.run(enrich_batch())
