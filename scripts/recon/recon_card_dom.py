"""Recon 2 : map page → DOM d'une carte recherche (nom enseigne, lien détail)."""
import asyncio
import json
import os

from playwright.async_api import async_playwright

EMAIL = os.environ["UNEMPLACEMENT_EMAIL"]
PASSWORD = os.environ["UNEMPLACEMENT_PASSWORD"]
OUT_DIR = "/zpool/one/maxime.debaugnies/data/recon_unemplacement"

RESPONSES = []


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            viewport={"width": 1600, "height": 1000},
            locale="fr-FR",
        )
        page = await ctx.new_page()

        async def on_response(resp):
            ct = resp.headers.get("content-type", "")
            if "json" in ct and "api.app" in resp.url:
                try:
                    body = await resp.text()
                except Exception:
                    body = "<unreadable>"
                RESPONSES.append({"url": resp.url, "body": body[:8000]})

        page.on("response", on_response)

        # Même flux que la recon qui a réussi : accès direct à la carte puis login
        await page.goto(
            "https://app.unemplacement.com/prospection_map/%C3%8Ele-de-France/0",
            wait_until="domcontentloaded", timeout=60000,
        )
        await page.wait_for_timeout(4000)
        print("URL initiale:", page.url)

        email_input = await page.query_selector("input[type='email'], input[name*='mail'], input[name='username']")
        pwd_input = await page.query_selector("input[type='password']")
        if pwd_input:
            print("Formulaire de login détecté")
            await email_input.fill(EMAIL)
            await pwd_input.fill(PASSWORD)
            btn = await page.query_selector("button[type='submit'], button:has-text('Connexion'), button:has-text('Se connecter')")
            if btn:
                await btn.click()
            else:
                await pwd_input.press("Enter")
            await page.wait_for_timeout(6000)
            print("URL après login:", page.url)
            await page.goto(
                "https://app.unemplacement.com/prospection_map/%C3%8Ele-de-France/0",
                wait_until="domcontentloaded", timeout=60000,
            )
        await page.wait_for_timeout(10000)
        print("URL carte:", page.url)
        await page.screenshot(path=f"{OUT_DIR}/card_01_map.png")

        # Dump de la structure DOM des cartes (cherche le nom d'enseigne dans le DOM)
        dom_info = await page.evaluate("""
          () => {
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            const names = [];
            let n;
            while ((n = walker.nextNode())) {
              const t = n.nodeValue.trim();
              if (t.length > 2 && t === t.toUpperCase() && /[A-Z]/.test(t) && t.length < 60) names.push(t);
            }
            return { uppercaseTexts: names.slice(0, 40), url: location.href };
          }
        """)
        print(json.dumps(dom_info, ensure_ascii=False, indent=1)[:1500])

        # Cherche les éléments cliquables de carte
        cards = await page.query_selector_all("[class*='prospection'], [class*='Prospection'], [class*='card'], [class*='Card']")
        print(f"{len(cards)} éléments carte-like trouvés")
        if cards:
            await cards[0].click()
            await page.wait_for_timeout(5000)
            print("URL après clic:", page.url)
            await page.screenshot(path=f"{OUT_DIR}/card_02_clicked.png")
            html = await page.content()
            with open(f"{OUT_DIR}/card_clicked.html", "w") as f:
                f.write(html)

        with open(f"{OUT_DIR}/card_responses.json", "w") as f:
            json.dump(RESPONSES, f, ensure_ascii=False, indent=1)
        print(f"{len(RESPONSES)} réponses API JSON capturées:")
        for r in RESPONSES:
            print("  -", r["url"][:110])

        await browser.close()


asyncio.run(main())
