"""
Nettoyage des SIREN sans établissement actif.

1. Récupère tous les SIREN de la table leads
2. Pour chaque batch, interroge l'API Sirene /siret en filtrant
   les établissements actifs (periode(etatAdministratifEtablissement:A))
3. Supprime les SIREN qui n'ont aucun établissement actif
"""

import requests
import time

SUPABASE_URL = "https://hxjryfaakdpwfgseirik.supabase.co"
SUPABASE_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imh4anJ5ZmFha2Rwd2Znc2VpcmlrIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MjkwMzgwMCwiZXhwIjoyMDk4NDc5ODAwfQ.gGba1EWAucnG7kaI2E__-lSWj1yAQjyEp2LpltFiKKw"
INSEE_API_KEY = "faf1d66f-9ab7-4986-b1d6-6f9ab7398604"
INSEE_SIRET_URL = "https://api.insee.fr/api-sirene/3.11/siret"

SUPABASE_PAGE_SIZE = 1000
BATCH_SIZE = 50
SLEEP_BETWEEN_BATCHES = 1.5
API_TIMEOUT = 60


def log(msg):
    print(msg, flush=True)


def supabase_headers():
    return {
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}",
        "Content-Type": "application/json",
    }


def fetch_all_sirens():
    """Récupère tous les SIREN distincts de la table leads."""
    sirens = []
    offset = 0
    while True:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/leads",
            headers={**supabase_headers(), "Range": f"{offset}-{offset + SUPABASE_PAGE_SIZE - 1}"},
            params={"select": "siren", "order": "siren"},
        )
        if resp.status_code == 416:
            break
        rows = resp.json()
        if not rows:
            break
        sirens.extend(r["siren"] for r in rows if r.get("siren"))
        if len(rows) < SUPABASE_PAGE_SIZE:
            break
        offset += SUPABASE_PAGE_SIZE
    return list(dict.fromkeys(sirens))


def query_active_siret_batch(sirens_batch, max_retries=3):
    """
    Interroge /siret pour un batch de SIREN, en filtrant uniquement
    les établissements actifs. Retourne (active_sirens, ok).
    Si ok=False, le batch n'a pas pu être vérifié et ne doit PAS être
    considéré comme inactif.
    """
    siren_query = " OR ".join(f"siren:{s}" for s in sirens_batch)
    q = f"({siren_query}) AND periode(etatAdministratifEtablissement:A)"

    headers = {
        "X-INSEE-Api-Key-Integration": INSEE_API_KEY,
        "Accept": "application/json",
    }

    active_sirens = set()
    total = 0
    debut = 0
    nombre = 1000

    while True:
        params = {
            "q": q,
            "nombre": str(nombre),
            "champs": "siren",
            "debut": str(debut),
        }

        resp = None
        for try_idx in range(max_retries):
            try:
                resp = requests.get(
                    INSEE_SIRET_URL,
                    headers=headers,
                    params=params,
                    timeout=API_TIMEOUT,
                )
            except requests.exceptions.Timeout:
                log(f"  ⚠ Timeout — réessai {try_idx + 1}/{max_retries}")
                time.sleep(5 * (try_idx + 1))
                continue
            except Exception as e:
                log(f"  ⚠ Erreur requête — {e}")
                time.sleep(5 * (try_idx + 1))
                continue

            if resp.status_code == 429:
                wait = 5 * (try_idx + 1)
                log(f"  ⏳ Rate limit — pause {wait}s…")
                time.sleep(wait)
                continue
            break

        if resp is None or resp.status_code != 200:
            status = resp.status_code if resp else "aucune réponse"
            text = resp.text[:200] if resp else ""
            log(f"  ⚠ HTTP {status} — {text}")
            return active_sirens, False

        try:
            data = resp.json()
        except Exception as e:
            log(f"  ⚠ Réponse JSON invalide — {e}")
            return active_sirens, False

        for etab in data.get("etablissements", []):
            siren = etab.get("siren", "")
            if siren:
                active_sirens.add(siren)

        total = data.get("header", {}).get("total", 0)
        if debut + nombre >= total:
            break
        debut += nombre
        log(f"  Pagination {sirens_batch[0]}… {debut}/{total}")

    return active_sirens, True


def delete_from_supabase(sirens_to_delete):
    """Supprime les leads pour les SIREN donnés."""
    deleted_leads = 0

    for i in range(0, len(sirens_to_delete), 50):
        batch = sirens_to_delete[i : i + 50]
        siren_filter = ",".join(batch)

        resp = requests.delete(
            f"{SUPABASE_URL}/rest/v1/leads",
            headers={**supabase_headers(), "Prefer": "return=representation"},
            params={"siren": f"in.({siren_filter})"},
        )
        if resp.status_code in (200, 204):
            try:
                deleted_leads += len(resp.json())
            except Exception:
                pass

        if (i // 50) % 10 == 0 and i > 0:
            log(f"  Suppression en cours… {deleted_leads} leads")

    return deleted_leads


def main():
    log("═══ Nettoyage des SIREN sans établissement actif ═══\n")

    log("1. Récupération des SIREN depuis Supabase…")
    all_sirens = fetch_all_sirens()
    log(f"   {len(all_sirens)} SIREN distincts\n")

    log("2. Vérification des établissements actifs via l'API Sirene…")
    active_sirens = set()
    failed_batches = []
    total_batches = (len(all_sirens) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(all_sirens), BATCH_SIZE):
        batch_num = i // BATCH_SIZE + 1
        batch = all_sirens[i : i + BATCH_SIZE]
        batch_active, ok = query_active_siret_batch(batch)

        if ok:
            active_sirens.update(batch_active)
        else:
            failed_batches.append(batch)
            log(f"  ⚠ Batch {batch_num} échoué, {len(batch)} SIREN mis de côté (pas de suppression)")

        if batch_num % 50 == 0 or batch_num == total_batches:
            log(f"   Batch {batch_num}/{total_batches} — {len(active_sirens)} SIREN avec au moins un établissement actif, {len(failed_batches)} batchs en échec")

        time.sleep(SLEEP_BETWEEN_BATCHES)

    if failed_batches:
        log(f"\n⚠ {sum(len(b) for b in failed_batches)} SIREN n'ont pas pu être vérifiés (pas supprimés)")

    closed_sirens = [s for s in all_sirens if s not in active_sirens and not any(s in b for b in failed_batches)]

    log(f"\n   Résultat : {len(active_sirens)} SIREN avec établissement actif, {len(closed_sirens)} à supprimer, {sum(len(b) for b in failed_batches)} non vérifiés")

    if not closed_sirens:
        log("\n✓ Aucun SIREN à supprimer")
        return

    log(f"\n3. Suppression de {len(closed_sirens)} SIREN de Supabase…")
    deleted_leads = delete_from_supabase(closed_sirens)
    log(f"   ✓ {deleted_leads} leads supprimés")

    log("\n═══ Nettoyage terminé ═══")
    log(f"  SIREN avec établissement actif : {len(active_sirens)}")
    log(f"  Non vérifiés (pas supprimés)  : {sum(len(b) for b in failed_batches)}")
    log(f"  Leads supprimés               : {deleted_leads}")


if __name__ == "__main__":
    main()
