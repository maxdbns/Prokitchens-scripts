"""
Enrichissement SIRENE — effectif de l'unité légale comme proxy de taille (point 5).
Cible les leads sans CA INPI et sans effectif déjà connu.
Batch de 100 SIREN par appel API INSEE pour rester dans les quotas.
"""

import os
import time
import requests
from datetime import datetime

import prokitchens_env
prokitchens_env.load_env()

# ─── Config ───
INSEE_API_KEY = os.environ.get("INSEE_API_KEY", "")
INSEE_SIREN_URL = "https://api.insee.fr/api-sirene/3.11/siren"

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY", "")
SUPABASE_TABLE = "leads"

BATCH_SIZE = 100
PAGE_SIZE = 500
REQUEST_DELAY = 0.5
LOG_FILE = "/zpool/one/maxime.debaugnies/logs/enrich_effectif_sirene.log"

TRANCHES = {
    "00": "0 salarié",
    "01": "1 à 2 salariés",
    "02": "3 à 5 salariés",
    "03": "6 à 9 salariés",
    "11": "10 à 19 salariés",
    "12": "20 à 49 salariés",
    "21": "50 à 99 salariés",
    "22": "100 à 199 salariés",
    "31": "200 à 249 salariés",
    "32": "250 à 499 salariés",
    "41": "500 à 999 salariés",
    "42": "1000 à 1999 salariés",
    "51": "2000 à 4999 salariés",
    "52": "5000 à 9999 salariés",
    "53": "10000 salariés et plus",
}


def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def supabase_headers():
    return {
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}",
        "Accept": "application/json",
    }


def supabase_write_headers():
    return {
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def fetch_leads(offset, limit):
    """Récupère les leads sans CA INPI ni effectif déjà connu."""
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}",
        params={
            "select": "siren,nom",
            "chiffre_affaires": "is.null",
            "tranche_effectifs_unite_legale": "is.null",
            "code_naf": "in.(56.10C,56.21Z)",
            "order": "score.desc.nullslast",
            "offset": offset,
            "limit": limit,
        },
        headers=supabase_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_effectifs_batch(sirens, retries=3):
    """Interroge l'API SIRENE sur un batch de SIREN."""
    if not sirens:
        return {}

    siren_query = " OR ".join(f"siren:{s}" for s in sirens)
    params = {
        "q": f"({siren_query})",
        "nombre": str(len(sirens)),
        "champs": "siren,trancheEffectifsUniteLegale,anneeEffectifsUniteLegale",
    }
    headers = {
        "X-INSEE-Api-Key-Integration": INSEE_API_KEY,
        "Accept": "application/json",
    }

    for attempt in range(retries):
        try:
            resp = requests.get(INSEE_SIREN_URL, params=params, headers=headers, timeout=30)
            if resp.status_code == 429:
                wait = 10 * (attempt + 1)
                log(f"  Rate limit INSEE, pause {wait}s...")
                time.sleep(wait)
                continue
            if resp.status_code == 404:
                return {}
            if resp.status_code != 200:
                log(f"  Erreur INSEE HTTP {resp.status_code}: {resp.text[:200]}")
                return {}

            data = resp.json()
            results = {}
            for ul in data.get("unitesLegales", []):
                siren = ul.get("siren")
                tranche = ul.get("trancheEffectifsUniteLegale")
                # "NN" = Non Nécessaire, pas de donnée exploitable
                if siren and tranche and tranche != "NN":
                    results[siren] = {
                        "tranche_effectifs_unite_legale": tranche,
                        "annee_effectifs_unite_legale": parse_int(ul.get("anneeEffectifsUniteLegale")),
                    }
            return results
        except Exception as e:
            log(f"  Erreur réseau INSEE: {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            return {}

    return {}


def parse_int(val):
    if not val:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def patch_lead(siren, data):
    try:
        resp = requests.patch(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}?siren=eq.{siren}",
            headers=supabase_write_headers(),
            json=data,
            timeout=30,
        )
        return resp.status_code in (200, 204)
    except Exception as e:
        log(f"  Erreur patch SIREN {siren}: {e}")
        return False


def main():
    log("=" * 60)
    log("Enrichissement SIRENE — effectifs unité légale")
    log("=" * 60)

    total_processed = 0
    total_found = 0
    offset = 0

    while True:
        leads = fetch_leads(offset, PAGE_SIZE)
        if not leads:
            log("Plus de leads à enrichir.")
            break

        for i in range(0, len(leads), BATCH_SIZE):
            batch = leads[i : i + BATCH_SIZE]
            sirens = [lead["siren"] for lead in batch if lead.get("siren")]

            effectifs = fetch_effectifs_batch(sirens)

            for lead in batch:
                siren = lead.get("siren")
                nom = lead.get("nom", "?")[:45]
                total_processed += 1

                data = effectifs.get(siren)
                if data and data.get("tranche_effectifs_unite_legale"):
                    total_found += 1
                    tranche = data["tranche_effectifs_unite_legale"]
                    label = TRANCHES.get(tranche, tranche)
                    log(f"  [{total_processed}] {nom:45s} -> {label}")
                    patch_lead(siren, data)
                else:
                    # Marque un NULL explicite pour ne pas re-tenter ce lead
                    patch_lead(siren, {"tranche_effectifs_unite_legale": None})

            if total_processed % 500 == 0:
                log(f"—— {total_processed} traités, {total_found} effectifs trouvés ——")

            time.sleep(REQUEST_DELAY)

        offset += len(leads)

    log("=" * 60)
    pct = (total_found / total_processed * 100) if total_processed else 0
    log(f"TERMINÉ: {total_processed} traités, {total_found} effectifs trouvés ({pct:.1f}%)")
    log("=" * 60)


if __name__ == "__main__":
    main()
