"""Capture les appels réseau de l'app UnEmplacement quand on ouvre une fiche
détail, pour identifier l'endpoint qui renvoie les commentaires."""
import os
import sys
import time

from playwright.sync_api import sync_playwright

EMAIL = os.environ["UNEMPLACEMENT_EMAIL"]
PASSWORD = os.environ["UNEMPLACEMENT_PASSWORD"]

DETAIL_URL = (
    "https://app.unemplacement.com/prospection_map/%C3%8Ele-de-France/0"
    "?id=1HN2dX28K43NuiQAGTas_region_28&locations=cmVnaW9uXzI4"
)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})

        def on_request(req):
            if "api.app.unemplacement.com" in req.url or "comment" in req.url.lower():
                body = (req.post_data or "")[:300]
                print(f">>> {req.method} {req.url}\n    {body}", flush=True)

        page.on("request", on_request)

        page.goto(
            "https://app.unemplacement.com/prospection_map/%C3%8Ele-de-France/0",
            wait_until="domcontentloaded",
        )
        page.wait_for_timeout(4000)
        if page.locator("input[type='password']").count() > 0:
            page.fill(
                "input[type='email'], input[name*='mail'], input[placeholder*='mail']", EMAIL
            )
            page.fill("input[type='password']", PASSWORD)
            btn = page.query_selector(
                "button[type='submit'], button:has-text('Connexion'), button:has-text('Se connecter')"
            )
            (btn.click() if btn else page.press("input[type='password']", "Enter"))
            page.wait_for_timeout(6000)

        print("=== ouverture fiche détail ===", flush=True)
        page.goto(DETAIL_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(12000)

        # clique éventuel sur un onglet commentaires
        for label in ["Commentaires", "commentaire", "Comment"]:
            loc = page.locator(f"text={label}")
            if loc.count() > 0:
                print(f"=== clic onglet '{label}' ===", flush=True)
                loc.first.click()
                page.wait_for_timeout(5000)
                break

        browser.close()


if __name__ == "__main__":
    main()
