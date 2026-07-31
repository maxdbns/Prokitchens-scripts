"""Reconnaissance UnEmplacement.com : login + découverte catégorie 'Recherche' + capture API."""
import asyncio
import json
import os
import re

from playwright.async_api import async_playwright

EMAIL = os.environ["UNEMPLACEMENT_EMAIL"]
PASSWORD = os.environ["UNEMPLACEMENT_PASSWORD"]
OUT_DIR = "/zpool/one/maxime.debaugnies/data/recon_unemplacement"

API_CAPTURES = []


async def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            viewport={"width": 1400, "height": 900},
            locale="fr-FR",
        )
        page = await ctx.new_page()

        # Capture des réponses JSON / API
        async def on_response(resp):
            url = resp.url
            ct = resp.headers.get("content-type", "")
            if "json" in ct or "/api/" in url or "graphql" in url.lower():
                if "unemplacement" in url or "cloudinary" not in url:
                    try:
                        body = await resp.text()
                    except Exception:
                        body = "<unreadable>"
                    API_CAPTURES.append({"url": url, "status": resp.status, "ct": ct, "body": body[:5000]})

        page.on("response", on_response)

        print("[1] Page d'accueil...")
        await page.goto("https://www.unemplacement.com/", wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(3000)
        await page.screenshot(path=f"{OUT_DIR}/01_home.png", full_page=False)

        # Liens visibles (catégories)
        links = await page.eval_on_selector_all(
            "a[href]",
            "els => els.map(e => ({href: e.href, text: (e.innerText||'').trim().slice(0,80)})).filter(l => l.text)",
        )
        seen = set()
        uniq = []
        for l in links:
            if l["href"] not in seen:
                seen.add(l["href"])
                uniq.append(l)
        with open(f"{OUT_DIR}/links_home.json", "w") as f:
            json.dump(uniq, f, ensure_ascii=False, indent=2)
        print(f"    {len(uniq)} liens uniques capturés")
        for l in uniq:
            if re.search(r"recherche|demande|locaux|annonce", l["href"] + l["text"], re.I):
                print("    *", l["text"][:60], "->", l["href"])

        print("[2] Login...")
        await page.goto("https://www.unemplacement.com/connexion", wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(2000)
        # Formulaire de connexion : sélecteurs génériques
        email_sel = "input[type='email'], input[name*='mail'], input[placeholder*='mail']"
        pass_sel = "input[type='password']"
        await page.fill(email_sel, EMAIL)
        await page.fill(pass_sel, PASSWORD)
        await page.screenshot(path=f"{OUT_DIR}/02_login_filled.png")
        # Soumission
        btn = await page.query_selector("button[type='submit'], button:has-text('Connexion'), button:has-text('Se connecter')")
        if btn:
            await btn.click()
        else:
            await page.press(pass_sel, "Enter")
        await page.wait_for_timeout(5000)
        await page.screenshot(path=f"{OUT_DIR}/03_after_login.png")
        print("    URL après login:", page.url)

        print("[3] Exploration des pages candidates...")
        candidates = [
            "https://www.unemplacement.com/recherche",
            "https://www.unemplacement.com/annonces",
            "https://www.unemplacement.com/demandes-locaux",
            "https://www.unemplacement.com/demandes",
            "https://www.unemplacement.com/recherches",
        ]
        for i, url in enumerate(candidates):
            try:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2500)
                status = resp.status if resp else "?"
                title = await page.title()
                print(f"    [{status}] {url} — {title!r}")
                await page.screenshot(path=f"{OUT_DIR}/04_page_{i}.png")
                html = await page.content()
                with open(f"{OUT_DIR}/page_{i}.html", "w") as f:
                    f.write(html)
            except Exception as e:
                print(f"    [ERR] {url}: {e}")

        with open(f"{OUT_DIR}/api_captures.json", "w") as f:
            json.dump(API_CAPTURES, f, ensure_ascii=False, indent=2)
        print(f"[4] {len(API_CAPTURES)} réponses JSON/API capturées -> api_captures.json")

        await browser.close()


asyncio.run(main())
