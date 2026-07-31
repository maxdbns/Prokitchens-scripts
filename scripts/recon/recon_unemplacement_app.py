"""Recon ciblée : app.unemplacement.com — prospection_map Île-de-France + capture réseau complète."""
import asyncio
import json
import os

from playwright.async_api import async_playwright

EMAIL = os.environ["UNEMPLACEMENT_EMAIL"]
PASSWORD = os.environ["UNEMPLACEMENT_PASSWORD"]
OUT_DIR = "/zpool/one/maxime.debaugnies/data/recon_unemplacement"
TARGET_URL = "https://app.unemplacement.com/prospection_map/%C3%8Ele-de-France/0"

REQUESTS = []
RESPONSES = []


async def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            viewport={"width": 1600, "height": 1000},
            locale="fr-FR",
        )
        page = await ctx.new_page()

        async def on_request(req):
            if any(k in req.url for k in ("api", "graphql", "search", "annonces", "demande", "prospect", "map", "geo")):
                REQUESTS.append({
                    "method": req.method,
                    "url": req.url,
                    "headers": {k: v for k, v in req.headers.items() if k.lower() in ("authorization", "x-api-key", "api-key", "content-type", "x-auth-token", "x-csrf-token")},
                    "post_data": (req.post_data or "")[:2000],
                })

        async def on_response(resp):
            url = resp.url
            ct = resp.headers.get("content-type", "")
            if "json" in ct:
                try:
                    body = await resp.text()
                except Exception:
                    body = "<unreadable>"
                RESPONSES.append({"url": url, "status": resp.status, "body": body[:20000]})

        page.on("request", on_request)
        page.on("response", on_response)

        print("[1] Accès direct à la carte (peut rediriger vers login)...")
        await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(4000)
        print("    URL:", page.url)
        await page.screenshot(path=f"{OUT_DIR}/app_01_initial.png")

        if "login" in page.url.lower() or "connexion" in page.url.lower() or await page.query_selector("input[type='password']"):
            print("[2] Login sur app.unemplacement.com...")
            email_sel = "input[type='email'], input[name*='mail'], input[placeholder*='mail'], input[name='username']"
            await page.fill(email_sel, EMAIL)
            await page.fill("input[type='password']", PASSWORD)
            btn = await page.query_selector("button[type='submit'], button:has-text('Connexion'), button:has-text('Se connecter')")
            if btn:
                await btn.click()
            else:
                await page.press("input[type='password']", "Enter")
            await page.wait_for_timeout(5000)
            print("    URL après login:", page.url)
            await page.screenshot(path=f"{OUT_DIR}/app_02_after_login.png")

            if "prospection_map" not in page.url:
                await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(5000)

        print("[3] Carte Île-de-France chargée, attente des données...")
        await page.wait_for_timeout(8000)
        await page.screenshot(path=f"{OUT_DIR}/app_03_map.png", full_page=False)
        html = await page.content()
        with open(f"{OUT_DIR}/app_map.html", "w") as f:
            f.write(html)

        # Interactions : chercher onglets / filtres "Recherche"
        buttons = await page.eval_on_selector_all(
            "button, a, [role='tab'], [class*='tab'], [class*='filter']",
            "els => els.map(e => ({tag: e.tagName, text: (e.innerText||'').trim().slice(0,60), cls: (e.className||'').toString().slice(0,80)})).filter(b => b.text)",
        )
        seen = set()
        uniq = []
        for b in buttons:
            key = b["text"]
            if key not in seen:
                seen.add(key)
                uniq.append(b)
        with open(f"{OUT_DIR}/app_buttons.json", "w") as f:
            json.dump(uniq[:100], f, ensure_ascii=False, indent=2)
        print(f"    {len(uniq)} boutons/onglets capturés")
        for b in uniq[:40]:
            print("    -", b["text"][:70])

        with open(f"{OUT_DIR}/app_requests.json", "w") as f:
            json.dump(REQUESTS, f, ensure_ascii=False, indent=2)
        with open(f"{OUT_DIR}/app_responses.json", "w") as f:
            json.dump(RESPONSES, f, ensure_ascii=False, indent=2)
        print(f"[4] {len(REQUESTS)} requêtes ciblées, {len(RESPONSES)} réponses JSON capturées")
        for r in RESPONSES[:15]:
            print(f"    [{r['status']}] {r['url'][:120]} ({len(r['body'])} chars)")

        await browser.close()


asyncio.run(main())
