"""
Vérifie les 100 SIREN du batch 234 de cleanup_closed_sirets.py
qui ont échoué (timeout / pas de réponse HTTP).
"""

import requests
import time

SUPABASE_URL = "https://hxjryfaakdpwfgseirik.supabase.co"
SUPABASE_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imh4anJ5ZmFha2Rwd2Znc2VpcmlrIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MjkwMzgwMCwiZXhwIjoyMDk4NDc5ODAwfQ.gGba1EWAucnG7kaI2E__-lSWj1yAQjyEp2LpltFiKKw"
INSEE_API_KEY = "faf1d66f-9ab7-4986-b1d6-6f9ab7398604"
INSEE_SIRET_URL = "https://api.insee.fr/api-sirene/3.11/siret"


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


def check_active(sirens_batch, max_retries=10):
    siren_query = " OR ".join(f"siren:{s}" for s in sirens_batch)
    q = f"({siren_query}) AND periode(etatAdministratifEtablissement:A)"

    headers = {
        "X-INSEE-Api-Key-Integration": INSEE_API_KEY,
        "Accept": "application/json",
    }

    active = set()
    debut = 0
    nombre = 1000
    ok = False

    for attempt in range(max_retries):
        try:
            resp = requests.get(
                INSEE_SIRET_URL,
                headers=headers,
                params={"q": q, "nombre": str(nombre), "champs": "siren", "debut": str(debut)},
                timeout=60,
            )
        except Exception as e:
            print(f"  ⚠ Tentative {attempt + 1}/{max_retries} échouée : {e}")
            time.sleep(5 * (attempt + 1))
            continue

        if resp.status_code == 429:
            wait = 5 * (attempt + 1)
            print(f"  ⏳ Rate limit — pause {wait}s…")
            time.sleep(wait)
            continue

        if resp.status_code != 200:
            print(f"  ⚠ HTTP {resp.status_code} — {resp.text[:200]}")
            time.sleep(5 * (attempt + 1))
            continue

        try:
            data = resp.json()
        except Exception as e:
            print(f"  ⚠ JSON invalide : {e}")
            time.sleep(5 * (attempt + 1))
            continue

        for etab in data.get("etablissements", []):
            siren = etab.get("siren", "")
            if siren:
                active.add(siren)

        total = data.get("header", {}).get("total", 0)
        if debut + nombre >= total:
            ok = True
            break
        debut += nombre
        print(f"  Pagination… {debut}/{total}")

    return active, ok


def main():
    print("Récupération des SIREN depuis Supabase…")
    all_sirens = fetch_all_sirens()
    print(f"  {len(all_sirens)} SIREN au total")

    # Batch 234 = indices 23300-23399 (batch size 100, 1-based)
    start = 233 * 100
    end = start + 100
    if end > len(all_sirens):
        end = len(all_sirens)

    failed_sirens = all_sirens[start:end]
    print(f"\nVérification des {len(failed_sirens)} SIREN du batch 234 (indices {start}-{end-1})")
    print("Découpage en sous-batchs de 25 pour éviter l'erreur 414…")

    all_active = set()
    all_inactive = []
    unverified = []

    for sub_start in range(0, len(failed_sirens), 25):
        sub_batch = failed_sirens[sub_start : sub_start + 25]
        print(f"  Sous-batch {sub_start // 25 + 1}/{(len(failed_sirens) + 24) // 25} : {len(sub_batch)} SIREN")
        active, ok = check_active(sub_batch)
        if ok:
            all_active.update(active)
            all_inactive.extend([s for s in sub_batch if s not in active])
        else:
            unverified.extend(sub_batch)
            print(f"    ⚠ Sous-batch non vérifié")
        time.sleep(2)

    print(f"\n✓ Vérification terminée : {len(all_active)} actifs, {len(all_inactive)} inactifs, {len(unverified)} non vérifiés")

    if all_inactive:
        print(f"\nSuppression de {len(all_inactive)} SIREN inactifs…")
        for i in range(0, len(all_inactive), 50):
            chunk = all_inactive[i : i + 50]
            siren_filter = ",".join(chunk)
            resp = requests.delete(
                f"{SUPABASE_URL}/rest/v1/leads",
                headers={**supabase_headers(), "Prefer": "return=representation"},
                params={"siren": f"in.({siren_filter})"},
            )
            if resp.status_code in (200, 204):
                print(f"  Supprimé {len(chunk)} SIREN")
            else:
                print(f"  ⚠ Échec suppression HTTP {resp.status_code}")
        print("\nTerminé.")
    else:
        print("\nAucun SIREN à supprimer dans ce batch.")


if __name__ == "__main__":
    main()
