"""Teste si /prospection_map/all/<page> pagine au niveau national."""
from playwright.sync_api import sync_playwright

EMAIL = __import__("os").environ["UNEMPLACEMENT_EMAIL"]
PASSWORD = __import__("os").environ["UNEMPLACEMENT_PASSWORD"]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    page.goto("https://app.unemplacement.com/prospection_map/all/0", wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    if page.locator("input[type='password']").count() > 0:
        page.fill("input[type='email'], input[name*='mail'], input[placeholder*='mail']", EMAIL)
        page.fill("input[type='password']", PASSWORD)
        btn = page.query_selector("button[type='submit'], button:has-text('Connexion'), button:has-text('Se connecter')")
        (btn.click() if btn else page.press("input[type='password']", "Enter"))
        page.wait_for_timeout(6000)
        if "prospection_map" not in page.url:
            page.goto("https://app.unemplacement.com/prospection_map/all/0", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(6000)

    print("URL:", page.url)
    page.wait_for_timeout(4000)
    cards = page.locator(".MuiCardHeader-title div[title]")
    print(f"{cards.count()} cartes")
    for i in range(min(5, cards.count())):
        print(" ", cards.nth(i).get_attribute("title"))

    # Test page 1
    page.goto("https://app.unemplacement.com/prospection_map/all/1", wait_until="domcontentloaded")
    page.wait_for_timeout(6000)
    cards = page.locator(".MuiCardHeader-title div[title]")
    print(f"page 1: {cards.count()} cartes")
    for i in range(min(5, cards.count())):
        print(" ", cards.nth(i).get_attribute("title"))
    browser.close()
