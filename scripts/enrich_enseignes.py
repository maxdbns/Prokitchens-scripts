"""Enrichissement des noms d'enseigne ProFoods.

Les noms d'enseigne (LIDL, SUBWAY...) ne sont pas dans l'API fetch_prospections :
ils sont affichés dans le DOM (flux Firestore côté front). Ce script :
1. charge la liste nationale dans le navigateur et scrolle jusqu'à tout charger,
2. lit les titres des cartes dans l'ordre du DOM (= ordre de l'API, vérifié),
3. récupère les prospection_ids dans le même ordre via l'API,
4. met à jour profoods_demandes_clients.enseigne dans Supabase.

Usage : python3 scripts/enrich_enseignes.py [--dry-run]
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from run_guard import warn_if_zero

import requests
from playwright.sync_api import sync_playwright

EMAIL = os.environ["UNEMPLACEMENT_EMAIL"]
PASSWORD = os.environ["UNEMPLACEMENT_PASSWORD"]

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "recon"))
from test_unemplacement_api import get_id_token, fetch_prospections  # noqa: E402
MAP_URL = "https://app.unemplacement.com/prospection_map/{region}/0"
MAX_SCROLLS = 60

# L'API plafonne à 1000 résultats par requête : on segmente par région pour
# garder l'alignement DOM <-> API (chaque région reste sous le plafond).
REGIONS = [
    "Île-de-France",
    "Auvergne-Rhône-Alpes",
    "Nouvelle-Aquitaine",
    "Occitanie",
    "Provence-Alpes-Côte d'Azur",
    "Hauts-de-France",
    "Grand Est",
    "Bretagne",
    "Normandie",
    "Pays de la Loire",
    "Bourgogne-Franche-Comté",
    "Centre-Val de Loire",
    "Corse",
]

# Charge SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY depuis prokitchens-app/.env
if not os.environ.get("CI"):
    ENV_PATH = os.path.join(os.path.dirname(__file__), "..", "prokitchens-app", ".env")
    if os.path.exists(ENV_PATH):
        for line in open(ENV_PATH):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
SUPABASE_URL = os.environ["NEXT_PUBLIC_SUPABASE_URL"].rstrip("/")
SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]


def fetch_region_api_items(token, region):
    """Recherches d'une région via l'API, dans l'ordre (20/page)."""
    first = fetch_prospections(token, page=0, state=region)
    items = list(first[0])
    total = first[2] if isinstance(first[2], int) else len(first[0])
    page = 1
    while len(items) < total and page < 50:
        data = fetch_prospections(token, page=page, state=region)
        batch = data[0]
        if not batch:
            break
        items.extend(batch)
        page += 1
    return items


def collect_dom_titles(page, region):
    """Titres des cartes d'une région via scroll infini (page Playwright connectée)."""
    from urllib.parse import quote

    page.goto(MAP_URL.format(region=quote(region)), wait_until="domcontentloaded")
    page.wait_for_timeout(8000)
    cards = page.locator(".MuiCardHeader-title div[title]")
    prev, stable = 0, 0
    for _ in range(MAX_SCROLLS):
        count = cards.count()
        if count == prev:
            stable += 1
            if stable >= 3:
                break
        else:
            stable = 0
        prev = count
        page.mouse.wheel(0, 3000)
        page.wait_for_timeout(2200)
    return [cards.nth(i).get_attribute("title") or "" for i in range(cards.count())]


def supabase_update_enseigne(pid, enseigne):
    for attempt in range(3):
        try:
            r = requests.patch(
                f"{SUPABASE_URL}/rest/v1/profoods_demandes_clients?id_annonce=eq.{pid}",
                headers={
                    "apikey": SERVICE_KEY,
                    "Authorization": f"Bearer {SERVICE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
                json={"enseigne": enseigne},
                timeout=30,
            )
            return r.status_code in (200, 204)
        except requests.exceptions.RequestException:
            if attempt == 2:
                return False
            time.sleep(2 * (attempt + 1))
    return False


def main():
    dry = "--dry-run" in sys.argv
    from playwright.sync_api import sync_playwright

    token = get_id_token()
    mapping = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.goto(MAP_URL.format(region="%C3%8Ele-de-France"), wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        if page.locator("input[type='password']").count() > 0:
            page.fill("input[type='email'], input[name*='mail'], input[placeholder*='mail']", EMAIL)
            page.fill("input[type='password']", PASSWORD)
            btn = page.query_selector(
                "button[type='submit'], button:has-text('Connexion'), button:has-text('Se connecter')"
            )
            (btn.click() if btn else page.press("input[type='password']", "Enter"))
            page.wait_for_timeout(6000)

        for region in REGIONS:
            items = fetch_region_api_items(token, region)
            titles = collect_dom_titles(page, region)
            n = min(len(items), len(titles))
            region_mapped = 0
            for i in range(n):
                pid = items[i].get("prospection_id") or items[i].get("id")
                name = (titles[i] or "").strip()
                if pid and name:
                    mapping[pid] = name
                    region_mapped += 1
            print(f"  {region}: {len(items)} API / {len(titles)} DOM -> {region_mapped} noms")
            if len(items) > 0 and len(titles) > 0:
                print(f"    check[0]: ref={items[0].get('reference_id')} -> '{titles[0]}'")

        browser.close()

    print(f"Total: {len(mapping)} noms mappés")
    if dry:
        print("[dry-run] pas d'écriture Supabase")
        return

    print("Mise à jour Supabase...")
    ok = 0
    for pid, name in mapping.items():
        if supabase_update_enseigne(pid, name):
            ok += 1
        time.sleep(0.05)
    print(f"  {ok}/{len(mapping)} lignes mises à jour")
    warn_if_zero("Enrich enseignes : noms mappés", len(mapping))
    if mapping:
        warn_if_zero("Enrich enseignes : lignes mises à jour", ok)


if __name__ == "__main__":
    main()
