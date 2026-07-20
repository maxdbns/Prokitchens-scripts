"""
Nettoyage des leads en procédure collective (redressement judiciaire, liquidation, sauvegarde)
via l'API BODACC (data.gouv.fr / opendatasoft).
"""

import requests
import time
import os
from datetime import datetime

SUPABASE_URL = "https://hxjryfaakdpwfgseirik.supabase.co"
SUPABASE_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imh4anJ5ZmFha2Rwd2Znc2VpcmlrIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MjkwMzgwMCwiZXhwIjoyMDk4NDc5ODAwfQ.gGba1EWAucnG7kaI2E__-lSWj1yAQjyEp2LpltFiKKw"

BODACC_API = "https://bodacc-datadila.opendatasoft.com/api/records/1.0/search"
BODACC_DATASET = "annonces-commerciales"

BATCH_SIZE = 80
REQUEST_DELAY = 0.8
LOG_FILE = "/zpool/one/maxime.debaugnies/cleanup_redressement_judiciaire.log"


def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def supabase_headers():
    return {
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}",
        "Content-Type": "application/json",
    }


def fetch_all_sirens():
    sirens = []
    offset = 0
    page_size = 1000
    while True:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/leads",
            headers={**supabase_headers(), "Range": f"{offset}-{offset + page_size - 1}"},
            params={"select": "siren", "order": "siren"},
            timeout=30,
        )
        if resp.status_code == 416:
            break
        rows = resp.json()
        if not rows:
            break
        sirens.extend(r["siren"] for r in rows if r.get("siren"))
        if len(rows) < page_size:
            break
        offset += page_size
    return list(dict.fromkeys(sirens))


def check_bodacc_batch(sirens_batch):
    """Vérifie si un batch de SIREN a des procédures collectives dans le BODACC."""
    query = " OR ".join(f"registre:{s}" for s in sirens_batch)
    params = {
        "dataset": BODACC_DATASET,
        "rows": 1000,
        "q": f"({query}) AND familleavis:collective",
    }

    try:
        resp = requests.get(BODACC_API, params=params, timeout=30)
    except requests.RequestException as e:
        log(f"  Erreur BODACC: {e}")
        return set()

    if resp.status_code != 200:
        log(f"  BODACC HTTP {resp.status_code}: {resp.text[:200]}")
        return set()

    data = resp.json()
    records = data.get("records", [])
    affected_sirens = set()

    for record in records:
        registre = record.get("fields", {}).get("registre", "")
        for part in registre.split(","):
            clean = part.strip().replace(" ", "")
            if clean.isdigit() and len(clean) == 9:
                affected_sirens.add(clean)

    return affected_sirens


def delete_from_supabase(sirens_to_delete):
    deleted_leads = 0
    deleted_etabs = 0

    for i in range(0, len(sirens_to_delete), 50):
        batch = sirens_to_delete[i : i + 50]
        siren_filter = ",".join(batch)

        resp = requests.delete(
            f"{SUPABASE_URL}/rest/v1/etablissements",
            headers={**supabase_headers(), "Prefer": "return=representation"},
            params={"siren": f"in.({siren_filter})"},
            timeout=30,
        )
        if resp.status_code in (200, 204):
            try:
                deleted_etabs += len(resp.json())
            except Exception:
                pass

        resp = requests.delete(
            f"{SUPABASE_URL}/rest/v1/leads",
            headers={**supabase_headers(), "Prefer": "return=representation"},
            params={"siren": f"in.({siren_filter})"},
            timeout=30,
        )
        if resp.status_code in (200, 204):
            try:
                deleted_leads += len(resp.json())
            except Exception:
                pass

        if (i // 50) % 10 == 0 and i > 0:
            log(f"  Suppression en cours... {deleted_leads} leads, {deleted_etabs} établissements")

    return deleted_leads, deleted_etabs


def main():
    log("═══ Nettoyage des leads en procédure collective (BODACC) ═══")

    log("1. Récupération des SIREN depuis Supabase...")
    all_sirens = fetch_all_sirens()
    log(f"   {len(all_sirens)} SIREN distincts")

    log("2. Vérification via l'API BODACC...")
    collective_sirens = []
    total_batches = (len(all_sirens) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(all_sirens), BATCH_SIZE):
        batch_num = i // BATCH_SIZE + 1
        batch = all_sirens[i : i + BATCH_SIZE]
        affected = check_bodacc_batch(batch)
        collective_sirens.extend(affected)

        if batch_num % 50 == 0 or batch_num == total_batches:
            log(f"   Batch {batch_num}/{total_batches} — {len(collective_sirens)} procédures collectives trouvées")

        time.sleep(REQUEST_DELAY)

    log(f"\n   Résultat : {len(collective_sirens)} SIREN en procédure collective")

    if not collective_sirens:
        log("\n✓ Aucune procédure collective trouvée !")
        return

    log(f"\n3. Suppression de {len(collective_sirens)} leads de Supabase...")
    deleted_leads, deleted_etabs = delete_from_supabase(list(collective_sirens))
    log(f"   ✓ {deleted_leads} leads et {deleted_etabs} établissements supprimés")

    log("\n═══ Nettoyage terminé ═══")


if __name__ == "__main__":
    main()
