"""Recon : clic sur une carte 'Recherche' pour trouver l'URL de détail et le nom de l'enseigne."""
import asyncio
import json
import os

from playwright.async_api import async_playwright

EMAIL = os.environ["UNEMPLACEMENT_EMAIL"]
PASSWORD = os.environ["UNEMPLACEMENT_PASSWORD"]
TARGET_URL = "https://app.unemplacement.com/prospection_map/%C3%8Ele-de-France/0"
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
            if "json" in ct and "api" in resp.url:
                try:
                    body = await resp.text()
                except Exception:
                    body = "<unreadable>"
                RESPONSES.append({"url": resp.url, "status": resp.status, "body": body[:15000]})

        page.on("response", on_response)

        await page.goto("https://app.unemplacement.com/", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(3000)
        if await page.query_selector("input[type='password']"):
            await page.fill("input[type='email'], input[name*='mail']", EMAIL)
            await page.fill("input[type='password']", PASSWORD)
            btn = await page.query_selector("button[type='submit'], button:has-text('Connexion')")
            if btn:
                await btn.click()
            else:
                await page.press("input[type='password']", "Enter")
            await page.wait_for_timeout(5000)

        await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(8000)
        print("URL carte:", page.url)

        # Onglet RECHERCHES
        tab = await page.query_selector("text=RECHERCHES")
        if tab:
            await tab.click()
            await page.wait_for_timeout(4000)
        await page.screenshot(path=f"{OUT_DIR}/detail_01_recherches_tab.png")

        # Clic sur la première carte de recherche
        card = await page.query_selector("[class*='card'], [class*='Card'], [class*='prospection'], [class*='item']")
        if card:
            await card.click()
            await page.wait_for_timeout(4000)
        print("URL après clic carte:", page.url)
        await page.screenshot(path=f"{OUT_DIR}/detail_02_card_clicked.png")

        html = await page.content()
        with open(f"{OUT_DIR}/detail_card.html", "w") as f:
            f.write(html)

        # Tous les liens visibles après ouverture
        links = await page.eval_on_selector_all(
            "a[href]",
            "els => els.map(e => ({href: e.href, text: (e.innerText||'').trim().slice(0,60)})).filter(l => l.text)",
        )
        print("Liens visibles:")
        for l in links[:30]:
            print("  -", l["text"][:50], "->", l["href"][:120])

        with open(f"{OUT_DIR}/detail_responses.json", "w") as f:
            json.dump(RESPONSES, f, ensure_ascii=False, indent=1)
        print(f"\n{len(RESPONSES)} réponses JSON capturées")
        for r in RESPONSES:
            print(f"  [{r['status']}] {r['url'][:110]}")

        await browser.close()


asyncio.run(main())
