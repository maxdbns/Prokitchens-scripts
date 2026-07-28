"""
Enrichissement INPI — QSR Paris (NAF 56.10C, 75xxx)
Tourne en tâche de fond, s'arrête automatiquement à 9 500 requêtes (marge de sécurité sur le quota 10K/jour).
Relancer chaque jour jusqu'à épuisement.
"""

import requests
import time
import json
import sys
from datetime import datetime

# ─── Config ───
INPI_USERNAME = "maxime.debaugnies@cloudkitchens.com"
INPI_PASSWORD = "Thomas36130!"
INPI_BASE_URL = "https://registre-national-entreprises.inpi.fr/api"

SUPABASE_URL = "https://hxjryfaakdpwfgseirik.supabase.co"
SUPABASE_API_KEY = "sb_publishable_a7xpn8srwByQrW1rXwpdlw_eQnwAoHT"
SUPABASE_TABLE = "leads"

DAILY_QUOTA = 9500
REQUEST_DELAY = 0.35
BATCH_SIZE = 1000
LOG_FILE = "/zpool/one/maxime.debaugnies/logs/inpi_enrich_qsr_paris.log"


def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def inpi_login():
    resp = requests.post(
        f"{INPI_BASE_URL}/sso/login",
        json={"username": INPI_USERNAME, "password": INPI_PASSWORD},
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    log("Connecté à l'API INPI")
    return resp.json()["token"]


def fetch_leads(limit):
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}",
        params={
            "select": "siren,nom,ville",
            "code_naf": "eq.56.10C",
            "code_postal": "like.75*",
            "enriched_inpi": "eq.false",
            "limit": limit,
        },
        headers={
            "apikey": SUPABASE_API_KEY,
            "Authorization": f"Bearer {SUPABASE_API_KEY}",
            "Accept": "application/json",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def parse_montant(val):
    if not val:
        return None
    try:
        return int(val.strip())
    except (ValueError, TypeError):
        return None


def extract_financial_data(bilan_saisi):
    bilan = bilan_saisi.get("bilanSaisi", {}).get("bilan", {})
    identite = bilan.get("identite", {})
    date_cloture = identite.get("dateClotureExercice", "")

    ca = None
    resultat_net = None

    for page in bilan.get("detail", {}).get("pages", []):
        for liasse in page.get("liasses", []):
            code = liasse.get("code", "")
            if code == "FL":
                ca = parse_montant(liasse.get("m3") or liasse.get("m1"))
            elif code == "FJ" and ca is None:
                ca = parse_montant(liasse.get("m3") or liasse.get("m1"))
            elif code == "HN":
                resultat_net = parse_montant(liasse.get("m1"))

    if ca is None and resultat_net is None:
        return None

    return {
        "chiffre_affaires": ca,
        "resultat_net": resultat_net,
        "date_cloture_bilan": date_cloture,
    }


def get_financial_data(siren, headers):
    try:
        resp = requests.get(
            f"{INPI_BASE_URL}/companies/{siren}/attachments",
            headers=headers,
            timeout=30,
        )
    except requests.RequestException as e:
        log(f"  Erreur réseau SIREN {siren}: {e}")
        return None

    if resp.status_code == 404:
        return None
    if resp.status_code == 429:
        log("  Rate limit atteint, pause 60s...")
        time.sleep(60)
        return get_financial_data(siren, headers)
    if resp.status_code == 401:
        return "REAUTH"
    if resp.status_code != 200:
        return None

    bilans_saisis = resp.json().get("bilansSaisis", [])
    for bs in bilans_saisis:
        if bs.get("confidentiality") == "Public" and not bs.get("deleted", False):
            return extract_financial_data(bs)
    return None


def patch_lead(siren, financial_data):
    patch = {"enriched_inpi": True}
    if financial_data:
        if financial_data["chiffre_affaires"] is not None:
            patch["chiffre_affaires"] = financial_data["chiffre_affaires"]
        if financial_data["resultat_net"] is not None:
            patch["resultat_net"] = financial_data["resultat_net"]
        if financial_data["date_cloture_bilan"]:
            patch["date_cloture_bilan"] = financial_data["date_cloture_bilan"]

    resp = requests.patch(
        f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}?siren=eq.{siren}",
        headers={
            "apikey": SUPABASE_API_KEY,
            "Authorization": f"Bearer {SUPABASE_API_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        json=patch,
        timeout=30,
    )
    return resp.status_code in (200, 204)


def main():
    log("=" * 60)
    log("Démarrage enrichissement INPI — QSR Paris (56.10C, 75xxx)")
    log("=" * 60)

    token = inpi_login()
    headers = {"Authorization": f"Bearer {token}"}

    total_processed = 0
    total_ca_found = 0
    total_no_bilan = 0
    api_calls = 0

    while api_calls < DAILY_QUOTA:
        remaining = DAILY_QUOTA - api_calls
        batch_size = min(BATCH_SIZE, remaining)

        leads = fetch_leads(batch_size)
        if not leads:
            log("Plus aucun lead QSR Paris à enrichir !")
            break

        log(f"Batch de {len(leads)} leads (API calls: {api_calls}/{DAILY_QUOTA})")

        for i, lead in enumerate(leads):
            if api_calls >= DAILY_QUOTA:
                log(f"Quota journalier atteint ({DAILY_QUOTA} requêtes)")
                break

            siren = lead["siren"]
            nom = lead.get("nom", "?")[:45]

            financial = get_financial_data(siren, headers)
            api_calls += 1

            if financial == "REAUTH":
                log("Token expiré, reconnexion...")
                token = inpi_login()
                headers = {"Authorization": f"Bearer {token}"}
                financial = get_financial_data(siren, headers)
                api_calls += 1

            if financial:
                ca = financial.get("chiffre_affaires")
                rn = financial.get("resultat_net")
                total_ca_found += 1
                detail = f"CA={ca:,}€" if ca else ""
                if rn:
                    detail += f" RN={rn:,}€"
                log(f"  [{total_processed+1}] {nom:45s} ✓ {detail}")
            else:
                total_no_bilan += 1

            patch_lead(siren, financial)
            total_processed += 1

            if total_processed % 500 == 0:
                pct = (total_ca_found / total_processed * 100) if total_processed else 0
                log(f"── Progression: {total_processed} traités, {total_ca_found} CA ({pct:.1f}%), {api_calls} appels API ──")

            time.sleep(REQUEST_DELAY)

    log("=" * 60)
    pct = (total_ca_found / total_processed * 100) if total_processed else 0
    log(f"TERMINÉ: {total_processed} traités, {total_ca_found} avec CA ({pct:.1f}%), {total_no_bilan} sans bilan")
    log(f"Appels API utilisés: {api_calls}/{DAILY_QUOTA}")
    log("=" * 60)


if __name__ == "__main__":
    main()
