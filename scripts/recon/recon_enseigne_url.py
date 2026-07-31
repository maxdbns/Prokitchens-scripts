"""Recon : pour chaque carte de recherche, extraire (enseigne, référence) et
vérifier s'il existe une URL par annonce après clic."""
import json
import re

from playwright.sync_api import sync_playwright

EMAIL = __import__("os").environ["UNEMPLACEMENT_EMAIL"]
PASSWORD = __import__("os").environ["UNEMPLACEMENT_PASSWORD"]
MAP_URL = "https://app.unemplacement.com/prospection_map/%C3%8Ele-de-France/0"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    page.goto(MAP_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(4000)

    # Login si nécessaire
    if page.locator('input[type="password"]').count() > 0:
        page.fill("input[type='email'], input[name*='mail'], input[placeholder*='mail']", EMAIL)
        page.fill("input[type='password']", PASSWORD)
        btn = page.query_selector("button[type='submit'], button:has-text('Connexion'), button:has-text('Se connecter')")
        if btn:
            btn.click()
        else:
            page.press("input[type='password']", "Enter")
        page.wait_for_timeout(6000)
        if "prospection_map" not in page.url:
            page.goto(MAP_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)

    print("URL après login:", page.url)

    # Attendre les cartes
    page.wait_for_timeout(5000)
    cards = page.locator('div[title]')
    titles = [c.get_attribute("title") for c in cards.all() if c.get_attribute("title")]
    print("titres visibles:", titles[:30])

    # Cartes de recherche : MuiCardHeader-title contient un div[title]
    card_titles = page.locator('.MuiCardHeader-title div[title]')
    n = card_titles.count()
    print(f"{n} cartes de recherche sur la page")
    for i in range(min(n, 5)):
        print(f"  carte {i}: {card_titles.nth(i).get_attribute('title')}")

    # Cliquer sur la première carte et observer URL + panneau détail
    if n > 0:
        url_avant = page.url
        card_titles.nth(0).click()
        page.wait_for_timeout(4000)
        print("URL avant clic:", url_avant)
        print("URL après clic:", page.url)

        # Chercher la référence dans le panneau détail
        body = page.content()
        refs = re.findall(r'([A-Z]{2}\d{2,6})', body)
        print("codes type référence dans la page:", refs[:15])
        m = re.search(r'[Rr]éf[ée]rence[^A-Z0-9]{0,40}([A-Z0-9]{3,10})', body)
        print("référence explicite:", m.group(1) if m else None)

        # Chercher un bouton lien/partage dans le détail
        for btn in page.locator('a[href]').all():
            href = btn.get_attribute("href") or ""
            if "unemplacement" in href and "static" not in href:
                print("lien trouvé:", href)

        page.screenshot(path="/zpool/one/maxime.debaugnies/data/recon_unemplacement/enseigne_detail.png")
        open("/zpool/one/maxime.debaugnies/data/recon_unemplacement/enseigne_detail.html", "w").write(body)

    browser.close()
