"""
Nettoyage des leads fermés/radiés.

1. Récupère tous les SIREN de Supabase
2. Vérifie leur statut via l'API Sirene (etatAdministratifUniteLegale)
3. Supprime les cessées (C) et introuvables de Supabase (leads + etablissements)
4. Nettoie le CSV leads_manquants_salesforce.csv
"""

import requests
import time
import csv
import os
import sys

SUPABASE_URL = "https://hxjryfaakdpwfgseirik.supabase.co"
SUPABASE_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imh4anJ5ZmFha2Rwd2Znc2VpcmlrIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MjkwMzgwMCwiZXhwIjoyMDk4NDc5ODAwfQ.gGba1EWAucnG7kaI2E__-lSWj1yAQjyEp2LpltFiKKw"
INSEE_API_KEY = "faf1d66f-9ab7-4986-b1d6-6f9ab7398604"
INSEE_SIREN_URL = "https://api.insee.fr/api-sirene/3.11/siren"

CSV_PATH = "leads_manquants_salesforce.csv"
BATCH_SIZE = 80
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


def check_sirens_batch(sirens_batch, max_retries=5):
    """Vérifie le statut d'un batch de SIREN via l'API Sirene.
    Retourne (results, ok) où results est un dict {siren: etat} et ok
    indique si le batch a été vérifié avec succès.
    """
    siren_query = " OR ".join(f"siren:{s}" for s in sirens_batch)
    q = f"({siren_query})"

    headers = {
        "X-INSEE-Api-Key-Integration": INSEE_API_KEY,
        "Accept": "application/json",
    }

    results = {}
    for attempt in range(max_retries):
        try:
            resp = requests.get(
                INSEE_SIREN_URL,
                headers=headers,
                params={"q": q, "nombre": str(len(sirens_batch)), "champs": "siren,etatAdministratifUniteLegale"},
                timeout=API_TIMEOUT,
            )
        except requests.exceptions.Timeout:
            log(f"  ⚠ Timeout — réessai {attempt + 1}/{max_retries}")
            time.sleep(5 * (attempt + 1))
            continue
        except Exception as e:
            log(f"  ⚠ Erreur requête — {e}")
            time.sleep(5 * (attempt + 1))
            continue

        if resp.status_code == 429:
            wait = 5 * (attempt + 1)
            log(f"  ⏳ Rate limit — pause {wait}s…")
            time.sleep(wait)
            continue
        break

    if resp.status_code == 404:
        for s in sirens_batch:
            results[s] = "not_found"
        return results, True

    if resp.status_code != 200:
        log(f"  ⚠ HTTP {resp.status_code} — {resp.text[:200]}")
        return results, False

    try:
        data = resp.json()
    except Exception as e:
        log(f"  ⚠ Réponse JSON invalide — {e}")
        return results, False

    for ul in data.get("unitesLegales", []):
        siren = ul.get("siren", "")
        periodes = ul.get("periodesUniteLegale", [])
        if periodes:
            etat = periodes[0].get("etatAdministratifUniteLegale", "A")
        else:
            etat = "A"
        results[siren] = etat

    for s in sirens_batch:
        if s not in results:
            results[s] = "not_found"

    return results, True


def count_leads_for_sirens(sirens_set):
    """Compte combien de leads dans Supabase ont un SIREN dans l'ensemble donné."""
    if not sirens_set:
        return 0

    total = 0
    sirens_list = list(sirens_set)
    for i in range(0, len(sirens_list), 50):
        batch = sirens_list[i : i + 50]
        siren_filter = ",".join(batch)

        resp = requests.head(
            f"{SUPABASE_URL}/rest/v1/leads",
            headers={**supabase_headers(), "Prefer": "count=exact"},
            params={"siren": f"in.({siren_filter})", "select": "siren"},
        )
        if resp.status_code != 200:
            continue

        content_range = resp.headers.get("Content-Range", "")
        if "/" in content_range:
            total += int(content_range.split("/")[-1])

    return total


def delete_from_supabase(sirens_to_delete):
    """Supprime les leads et établissements pour les SIREN donnés."""
    deleted_leads = 0
    deleted_etabs = 0

    for i in range(0, len(sirens_to_delete), 50):
        batch = sirens_to_delete[i : i + 50]
        siren_filter = ",".join(batch)

        resp = requests.delete(
            f"{SUPABASE_URL}/rest/v1/etablissements",
            headers={**supabase_headers(), "Prefer": "return=representation"},
            params={"siren": f"in.({siren_filter})"},
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
        )
        if resp.status_code in (200, 204):
            try:
                deleted_leads += len(resp.json())
            except Exception:
                pass

        if (i // 50) % 10 == 0 and i > 0:
            log(f"  Suppression en cours… {deleted_leads} leads, {deleted_etabs} établissements")

    return deleted_leads, deleted_etabs


def clean_csv(closed_sirens_set):
    """Supprime les lignes du CSV dont le SIREN est fermé/radié."""
    if not os.path.exists(CSV_PATH):
        log(f"⚠ CSV {CSV_PATH} introuvable, skip")
        return 0

    with open(CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    before = len(rows)
    rows_clean = [r for r in rows if r.get("SIREN") not in closed_sirens_set]
    removed = before - len(rows_clean)

    with open(CSV_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows_clean)

    log(f"  CSV : {before} → {len(rows_clean)} lignes ({removed} supprimées)")
    return removed


def main():
    log("═══ Nettoyage des leads fermés/radiés ═══\n")

    log("1. Récupération des SIREN depuis Supabase…")
    all_sirens = fetch_all_sirens()
    log(f"   {len(all_sirens)} SIREN distincts\n")

    log("2. Vérification des statuts via l'API Sirene…")
    closed_sirens = []
    active_count = 0
    not_found_count = 0
    failed_batches = []
    total_batches = (len(all_sirens) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(all_sirens), BATCH_SIZE):
        batch_num = i // BATCH_SIZE + 1
        batch = all_sirens[i : i + BATCH_SIZE]
        statuses, ok = check_sirens_batch(batch)

        if not ok:
            failed_batches.append(batch)
            log(f"  ⚠ Batch {batch_num} non vérifié, {len(batch)} SIREN mis de côté")
            continue

        for siren, etat in statuses.items():
            if etat == "C" or etat == "not_found":
                closed_sirens.append(siren)
                if etat == "not_found":
                    not_found_count += 1
            else:
                active_count += 1

        if batch_num % 50 == 0 or batch_num == total_batches:
            log(f"   Batch {batch_num}/{total_batches} — {active_count} actifs, {len(closed_sirens)} fermés/radiés ({not_found_count} introuvables)")

        time.sleep(1.5)

    log(f"\n   Résultat : {active_count} actifs, {len(closed_sirens)} à supprimer ({not_found_count} introuvables), {sum(len(b) for b in failed_batches)} non vérifiés")

    if not closed_sirens:
        log("\n✓ Aucun lead fermé/radié trouvé !")
        return

    # Vérification pre-delete : combien de leads correspondent réellement aux SIREN fermés
    expected_leads = count_leads_for_sirens(set(closed_sirens))
    log(f"\n  Leads correspondant aux SIREN fermés/radiés : {expected_leads}")

    log(f"\n3. Suppression de {len(closed_sirens)} SIREN de Supabase…")
    deleted_leads, deleted_etabs = delete_from_supabase(closed_sirens)
    log(f"   ✓ {deleted_leads} leads et {deleted_etabs} établissements supprimés")

    # Vérification post-delete
    remaining_leads = count_leads_for_sirens(set(closed_sirens))
    log(f"   Leads restants avec ces SIREN (devrait être 0) : {remaining_leads}")
    if remaining_leads > 0:
        log(f"   ⚠ {remaining_leads} leads n'ont pas été supprimés")

    log(f"\n4. Nettoyage du CSV {CSV_PATH}…")
    closed_set = set(closed_sirens)
    clean_csv(closed_set)

    log(f"\n═══ Nettoyage terminé ═══")
    log(f"  Leads actifs restants : ~{active_count}")
    log(f"  Leads supprimés       : {deleted_leads} / {expected_leads} attendus")
    log(f"  Établissements supp.  : {deleted_etabs}")
    log(f"  Non vérifiés (pas supprimés) : {sum(len(b) for b in failed_batches)}")
    if remaining_leads > 0:
        log(f"  ⚠ Leads restants avec SIREN fermés : {remaining_leads}")


if __name__ == "__main__":
    main()
