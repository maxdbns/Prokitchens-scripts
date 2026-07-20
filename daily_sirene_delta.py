"""
Daily Sirene delta — récupère les nouveaux établissements, mises à jour et fermetures
pour les NAF cibles (56.10C, 56.21Z, 56.29B) sur les zones ProKitchens,
puis upsert les changements dans Supabase.

Fréquence conseillée : quotidien, car l'API Sirene permet de filtrer par date de
création / dernier traitement, ce qui réduit drastiquement le volume.
"""

import os
import sys
import csv
import time
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any, Set, Tuple

from check_bob import est_dans_bob, charger_book, normaliser_nom

# ─── Config ───
INSEE_API_KEY = os.environ.get("INSEE_API_KEY", "faf1d66f-9ab7-4986-b1d6-6f9ab7398604")
INSEE_SIRET_URL = "https://api.insee.fr/api-sirene/3.11/siret"

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://hxjryfaakdpwfgseirik.supabase.co")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY", "sb_publishable_a7xpn8srwByQrW1rXwpdlw_eQnwAoHT")
SUPABASE_TABLE = os.environ.get("SUPABASE_TABLE", "leads")

NAFS_CIBLES = {"56.10C", "56.21Z", "56.29B"}
ZONES = {
    "Île-de-France": ["75", "77", "78", "91", "92", "93", "94", "95"],
    "Lyon": ["69"],
    "Lille": ["59", "62"],
    "Marseille": ["13", "83", "84"],
}
PAGE_SIZE = 1000
UPSERT_BATCH_SIZE = 50
REQUEST_DELAY = 0.5
LOG_FILE = "/zpool/one/maxime.debaugnies/daily_sirene_delta.log"

# Marques exclues (copiées de verify_final_100.py pour cohérence)
EXCLUDED_BRANDS = {
    "MC DONALD", "MCDONALD", "BURGER KING", "KFC", "SUBWAY", "QUICK",
    "PIZZA HUT", "DOMINO'S", "DOMINOS", "TACO BELL", "WENDY'S", "CHIPOTLE",
    "FIVE GUYS", "SHAKE SHACK", "O'TACOS", "O TACOS", "PRET A MANGER",
    "PRETAMANGER", "PAUL", "LA BRIOCHE DOREE", "BRIOCHE DOREE", "POMME DE PAIN",
    "MEZZO DI PASTA", "VAPIANO", "PLANET SUSHI", "EAT SUSHI", "SUSHI SHOP",
    "BAGELSTEIN", "BAGEL CORNER", "BIG FERNAND", "BIOBURGER", "COJEAN", "EXKI",
    "MEMPHIS COFFEE", "L'ARTISAN DU BURGER", "BURGER & FRIES", "FRESH BURRITOS",
    "HECTOR CHICKEN", "PEPE CHICKEN", "MASTER POULET", "POULET BRAISE",
    "CHICKEN STREET", "ORIGINAL CHICKEN", "TASTY CHICKEN", "TASTY CROUSTY",
    "PASTA PIZZA", "PITAYA", "POKAWA", "TACOS AVENUE", "TACOS KING", "TORTILLA",
    "KIMCHI", "DIM SUM", "BAO BAO", "WOK TO WALK", "RAMEN", "SUSHI BAR",
    "STARBUCKS", "JOE & THE JUICE", "SSP", "AUTOGRILL", "FRICHTI", "DUMBO",
    "COLUMBUS CAFE", "WAFFLE FACTORY", "ALICE PIZZA", "ALOHA POKE", "KIOSQUE PIZZA",
    "MOZZA", "BOKIT", "POKE ME", "DARK KITCHEN", "FAMILEAT", "MONOPRIX",
    "DAILYMONOP", "AMREST", "FOODCHERI", "LENOTRE", "POTEL & CHABOT", "DALLOYAU",
    "GARES SNCF", "SNCF", "AUCHAN", "CARREFOUR", "CASINO", "FRANPRIX", "LECLERC",
    "LIDL", "ALDI", "INTERMARCHE", "BK", "BKR", "POKE HOUSE", "COME",
    "CONCESSIONS GARES", "CONCESSIONS AEROPORTS", "PRET", "DAILY MONOP",
    "LA CROISSANTERIE", "CROISSANCE 5", "LAV'CAR", "LAV'LINGE", "INVESTISSEMENTS",
    "AGENCE TECHNOLOGIQUE", "COMMUNICATIONS", "DEVELOPPEMENT SAS", "CAFE DE FRANCE",
    "BOULANGERIES BG", "R.A.F", "R A F", "ALAIN JANIAUD", "SALIM BENYOUNES",
    "JOSUE LANOIX", "RIEM BECKER", "REX SUBS", "SOCIETE DES MAGASINS LOUIS",
    "AGTM GARES", "AGTM GARE", "RELAY", "LAGARDERE", "VINDEMIA FINANCES",
    "BOUBACAR MENDES", "VIAGIO", "ANTONIO ALVES DA SILVA", "ASHAK GABER AZIZ",
    "COTTI COFFEE", "COTTI", "KRISPY KREME", "DOUGHNUTS MANUFACTURING",
}


def log(msg: str):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def insee_headers() -> Dict[str, str]:
    return {
        "X-INSEE-Api-Key-Integration": INSEE_API_KEY,
        "Accept": "application/json",
    }


def supabase_read_headers() -> Dict[str, str]:
    return {
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}",
        "Accept": "application/json",
    }


def supabase_write_headers() -> Dict[str, str]:
    return {
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def is_excluded_brand(nom: str) -> bool:
    n = normaliser_nom(nom)
    for brand in EXCLUDED_BRANDS:
        if normaliser_nom(brand) in n:
            return True
    return False


def parse_etablissement(e: Dict[str, Any]) -> Dict[str, Any]:
    adresse = e.get("adresseEtablissement", {})
    periode = e.get("periodesEtablissement", [{}])[0]
    unite = e.get("uniteLegale", {})
    etat = periode.get("etatAdministratifEtablissement", "")
    code_naf = periode.get("activitePrincipaleEtablissement", "")
    denomination = (
        periode.get("enseigne1Etablissement")
        or unite.get("denominationUniteLegale")
        or f"{unite.get('prenomUsuelUniteLegale', '')} {unite.get('nomUniteLegale', '')}".strip()
        or "Inconnu"
    )
    return {
        "siren": e.get("siren", ""),
        "siret": e.get("siret", ""),
        "nom": denomination,
        "code_naf": code_naf,
        "ville": adresse.get("libelleCommuneEtablissement", ""),
        "code_postal": adresse.get("codePostalEtablissement", ""),
        "adresse": " ".join(filter(None, [
            adresse.get("numeroVoieEtablissement", ""),
            adresse.get("typeVoieEtablissement", ""),
            adresse.get("libelleVoieEtablissement", ""),
        ])),
        "etat_administratif": etat,
        "date_creation": periode.get("dateCreationEtablissement", ""),
        "date_dernier_traitement": periode.get("dateDernierTraitementEtablissement", ""),
        "date_fermeture": periode.get("dateFermetureEtablissement", ""),
        "statut": "nouveau",
    }


def build_naf_filter() -> str:
    return " OR ".join(f"activitePrincipaleEtablissement:{c}" for c in NAFS_CIBLES)


def build_query_date_window(date_from: str, date_to: str, mode: str) -> str:
    """Construit la requête Sirene selon le mode : creation, update, fermeture."""
    naf_filter = build_naf_filter()
    base = f"periode({naf_filter})"

    if mode == "creation":
        return f"{base} AND dateCreationEtablissement:[{date_from} TO {date_to}]"
    elif mode == "update":
        return f"{base} AND dateDernierTraitementEtablissement:[{date_from} TO {date_to}] AND NOT(dateCreationEtablissement:[{date_from} TO {date_to}])"
    elif mode == "fermeture":
        return f"{base} AND etatAdministratifEtablissement:F AND dateDernierTraitementEtablissement:[{date_from} TO {date_to}]"
    else:
        raise ValueError(f"Mode inconnu : {mode}")


def fetch_delta(query: str, mode_label: str) -> List[Dict[str, Any]]:
    """
    Interroge l'API Sirene avec un curseur et retourne les établissements trouvés.
    """
    headers = insee_headers()
    curseur = "*"
    rows: List[Dict[str, Any]] = []
    page = 0
    total = None

    log(f"══ Recherche delta : {mode_label}")
    log(f"  Query : {query[:120]}...")

    while True:
        page += 1
        params = {"q": query, "nombre": PAGE_SIZE, "curseur": curseur}

        for attempt in range(3):
            try:
                resp = requests.get(INSEE_SIRET_URL, headers=headers, params=params, timeout=30)
                if resp.status_code == 429:
                    wait = 10 * (attempt + 1)
                    log(f"  Rate limit INSEE, pause {wait}s...")
                    time.sleep(wait)
                    continue
                break
            except Exception as e:
                log(f"  Erreur réseau (tentative {attempt + 1}/3) : {e}")
                if attempt < 2:
                    time.sleep(2 ** attempt)
                else:
                    return rows

        if resp.status_code == 404:
            log(f"  Aucun résultat (404)")
            break
        if resp.status_code != 200:
            log(f"  Erreur INSEE HTTP {resp.status_code} : {resp.text[:200]}")
            break

        data = resp.json()
        etabs = data.get("etablissements", [])
        header = data.get("header", {})
        if total is None:
            total = header.get("total", 0)

        rows.extend(parse_etablissement(e) for e in etabs)
        log(f"  Page {page} : {len(rows)}/{total}")

        next_cursor = header.get("curseurSuivant")
        if not next_cursor or next_cursor == curseur or len(rows) >= total:
            break
        curseur = next_cursor
        time.sleep(REQUEST_DELAY)

    return rows


def deduplicate_and_filter(rows: List[Dict[str, Any]], book: List[str]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Déduplique par SIREN, garde le meilleur établissement (actif privilégié),
    exclut les marques connues et le BOB.
    """
    stats = {"total_brut": len(rows), "hors_zone": 0, "exclu_marque": 0, "exclu_bob": 0, "fermetures": 0, "gardes": 0}
    by_siren: Dict[str, Dict[str, Any]] = {}

    for r in rows:
        siren = r.get("siren")
        if not siren:
            continue

        # Garder l'établissement actif si on a un doublon ouvert/fermé
        existing = by_siren.get(siren)
        if existing is None or (existing.get("etat_administratif") != "A" and r.get("etat_administratif") == "A"):
            by_siren[siren] = r

    kept = []
    for siren, r in by_siren.items():
        nom = r.get("nom", "")

        # Vérifier le code postal / zone géographique
        cp = r.get("code_postal", "")
        dep = cp[:2] if len(cp) >= 2 else ""
        if dep in {"97", "98"}:  # DOM
            dep = cp[:3]
        in_zone = any(dep in deps for deps in ZONES.values())
        if not in_zone:
            stats["hors_zone"] += 1
            continue

        # Exclure marques connues
        if is_excluded_brand(nom):
            stats["exclu_marque"] += 1
            continue

        # Exclure BOB
        is_bob, match = est_dans_bob(nom, book)
        if is_bob:
            stats["exclu_bob"] += 1
            continue

        if r.get("etat_administratif") == "F":
            stats["fermetures"] += 1

        kept.append(r)

    stats["gardes"] = len(kept)
    return kept, stats


def fetch_existing_sirens(sirens: List[str]) -> Set[str]:
    """
    Récupère les SIREN déjà présents dans Supabase pour éviter les conflits inutiles.
    On interroge par paquets de 100 pour rester dans les limites URL.
    """
    existing: Set[str] = set()
    if not sirens:
        return existing

    for i in range(0, len(sirens), 100):
        batch = sirens[i : i + 100]
        siren_filter = ",".join(batch)
        try:
            resp = requests.get(
                f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}",
                params={
                    "select": "siren",
                    "siren": f"in.({siren_filter})",
                    "limit": 100,
                },
                headers=supabase_read_headers(),
                timeout=30,
            )
            if resp.status_code == 200:
                for row in resp.json():
                    existing.add(row.get("siren", ""))
        except Exception as e:
            log(f"  Erreur vérification Supabase : {e}")

    return existing


def upsert_leads(leads: List[Dict[str, Any]]) -> Tuple[int, int]:
    """Upsert les nouveaux leads dans Supabase par lots."""
    if not leads:
        return 0, 0

    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{SUPABASE_TABLE}?on_conflict=siren"
    headers = {
        **supabase_write_headers(),
        "Prefer": "return=minimal,resolution=merge-duplicates",
    }

    ok = 0
    ko = 0
    total_batches = (len(leads) + UPSERT_BATCH_SIZE - 1) // UPSERT_BATCH_SIZE

    for i in range(0, len(leads), UPSERT_BATCH_SIZE):
        batch = leads[i : i + UPSERT_BATCH_SIZE]
        batch_num = i // UPSERT_BATCH_SIZE + 1
        try:
            resp = requests.post(url, json=batch, headers=headers, timeout=30)
            if resp.status_code in (200, 201):
                ok += len(batch)
                log(f"  Lot {batch_num}/{total_batches} : {len(batch)} upsertés")
            else:
                ko += len(batch)
                log(f"  Lot {batch_num}/{total_batches} : échec HTTP {resp.status_code} — {resp.text[:200]}")
        except Exception as e:
            ko += len(batch)
            log(f"  Lot {batch_num}/{total_batches} : erreur réseau — {e}")

    return ok, ko


def mark_closed_sirens(closed_sirens: List[str]) -> Tuple[int, int]:
    """Marque les SIREN fermés comme 'ferme' dans Supabase."""
    if not closed_sirens:
        return 0, 0

    ok = 0
    ko = 0
    for siren in closed_sirens:
        try:
            resp = requests.patch(
                f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}?siren=eq.{siren}",
                headers=supabase_write_headers(),
                json={"statut": "ferme", "etat_administratif": "F"},
                timeout=30,
            )
            if resp.status_code in (200, 204):
                ok += 1
            else:
                ko += 1
                log(f"  Échec marquage fermeture {siren} : HTTP {resp.status_code}")
        except Exception as e:
            ko += 1
            log(f"  Erreur marquage fermeture {siren} : {e}")

    return ok, ko


def load_last_run_date() -> str:
    """Charge la date de dernier run depuis un fichier, ou hier par défaut."""
    marker = "/zpool/one/maxime.debaugnies/.daily_sirene_delta_last_run"
    if os.path.exists(marker):
        with open(marker, "r") as f:
            return f.read().strip()
    yesterday = datetime.now() - timedelta(days=1)
    return yesterday.strftime("%Y-%m-%d")


def save_last_run_date(date_str: str):
    """Sauvegarde la date de run pour la prochaine exécution."""
    marker = "/zpool/one/maxime.debaugnies/.daily_sirene_delta_last_run"
    with open(marker, "w") as f:
        f.write(date_str)


def main():
    log("=" * 60)
    log("Daily Sirene Delta — démarrage")
    log("=" * 60)

    today = datetime.now().strftime("%Y-%m-%d")
    date_from = load_last_run_date()
    date_to = today

    if date_from >= date_to:
        log(f"Dernière exécution ({date_from}) est déjà aujourd'hui. Rien à faire.")
        return

    log(f"Fenêtre de recherche : {date_from} TO {date_to}")

    book = charger_book()
    log(f"Book of business chargé : {len(book)} noms")

    # ─── 1. Nouveaux établissements ───
    creations = fetch_delta(build_query_date_window(date_from, date_to, "creation"), "nouvelles créations")
    time.sleep(REQUEST_DELAY)

    # ─── 2. Mises à jour ───
    updates = fetch_delta(build_query_date_window(date_from, date_to, "update"), "mises à jour")
    time.sleep(REQUEST_DELAY)

    # ─── 3. Fermetures ───
    fermetures = fetch_delta(build_query_date_window(date_from, date_to, "fermeture"), "fermetures")

    # Combiner créations + updates (même traitement : upsert potentiel)
    all_changes = creations + updates
    leads, stats = deduplicate_and_filter(all_changes, book)

    log("\n--- Statistiques delta ---")
    log(f"  Total brut récupéré : {stats['total_brut']}")
    log(f"  Hors zones cibles : {stats['hors_zone']}")
    log(f"  Exclus (marque connue) : {stats['exclu_marque']}")
    log(f"  Exclus (BOB) : {stats['exclu_bob']}")
    log(f"  Fermetures détectées : {stats['fermetures']}")
    log(f"  Leads retenus : {stats['gardes']}")

    # ─── Upsert des nouveaux / mis à jour ───
    new_leads = [r for r in leads if r.get("etat_administratif") != "F"]
    closed_sirens = [r.get("siren") for r in leads if r.get("etat_administratif") == "F" and r.get("siren")]

    # Vérifier lesquels existent déjà pour ne pas écraser inutilement
    if new_leads:
        sirens_to_check = [r.get("siren") for r in new_leads if r.get("siren")]
        existing = fetch_existing_sirens(sirens_to_check)
        truly_new = [r for r in new_leads if r.get("siren") not in existing]
        updates_existing = [r for r in new_leads if r.get("siren") in existing]
        log(f"  Vrais nouveaux : {len(truly_new)} | Mises à jour existantes : {len(updates_existing)}")
    else:
        truly_new = []
        updates_existing = []

    # On upsert tout (créations + updates) : merge-duplicates gère le conflit
    ok_upsert, ko_upsert = upsert_leads(new_leads)

    # ─── Marquer les fermetures ───
    ok_closed, ko_closed = mark_closed_sirens(closed_sirens)

    log("\n--- Résultat ---")
    log(f"  Leads upsertés : {ok_upsert} (échecs : {ko_upsert})")
    log(f"  Fermetures marquées : {ok_closed} (échecs : {ko_closed})")

    save_last_run_date(today)
    log(f"\nProchain run à partir de : {today}")
    log("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"ERREUR FATALE : {e}")
        sys.exit(1)
