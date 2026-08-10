"""
Daily Sirene delta — récupère les nouveaux établissements, mises à jour et fermetures
pour les NAF cibles (56.10C, 56.21Z, 56.29B) sur les zones ProKitchens,
puis upsert les changements dans Supabase (tables leads et etablissements),
rafraîchit les agrégats et recalcule les scores.

Fréquence conseillée : quotidien, car l'API Sirene permet de filtrer par date de
création / dernier traitement, ce qui réduit drastiquement le volume.
"""

import os
import sys
import csv
import time
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any, Set, Tuple, Optional

import prokitchens_env
prokitchens_env.load_env()

from check_bob import est_dans_bob, charger_book, normaliser_nom

# ─── Config ───
INSEE_API_KEY = os.environ.get("INSEE_API_KEY", "")
INSEE_SIRET_URL = "https://api.insee.fr/api-sirene/3.11/siret"

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY", "")

NAFS_CIBLES = {"56.10C", "56.21Z", "56.29B"}
ZONES = {
    "Île-de-France": ["75", "77", "78", "91", "92", "93", "94", "95"],
    "Lyon": ["69"],
    "Lille": ["59", "62"],
    "Marseille": ["13", "83", "84"],
}
DEPARTEMENT_TO_REGION = {
    "75": "Île-de-France", "77": "Île-de-France", "78": "Île-de-France",
    "91": "Île-de-France", "92": "Île-de-France", "93": "Île-de-France",
    "94": "Île-de-France", "95": "Île-de-France",
    "69": "Auvergne-Rhône-Alpes",
    "59": "Hauts-de-France", "62": "Hauts-de-France", "80": "Hauts-de-France",
    "13": "Provence-Alpes-Côte d'Azur", "83": "Provence-Alpes-Côte d'Azur", "84": "Provence-Alpes-Côte d'Azur",
}
FORME_JURIDIQUE_MAP = {
    "1000": "Entrepreneur individuel",
    "5410": "SARL unipersonnelle",
    "5422": "SARL",
    "5426": "SARL de famille",
    "5430": "SARL",
    "5431": "SARL unipersonnelle",
    "5432": "SARL d'exercice liberal",
    "5498": "SARL",
    "5499": "SA",
    "5520": "SAS",
    "5599": "SA a directoire",
    "5710": "SAS",
    "5720": "SASU",
}
EFFECTIF_MAP = {
    "00": "0", "01": "1-2", "02": "3-5", "03": "6-9",
    "11": "10-19", "12": "20-49", "21": "50-99", "22": "100-199",
    "31": "200-249", "32": "250-499", "41": "500-999", "42": "1000-1999",
    "51": "2000-4999", "52": "5000-9999", "53": "10000+",
}

PAGE_SIZE = 1000
LEAD_UPSERT_BATCH_SIZE = 50
ETAB_UPSERT_BATCH_SIZE = 10
LEAD_UPDATE_BATCH_SIZE = 50
CLOSED_DELETE_BATCH_SIZE = 10
REQUEST_DELAY = 0.5
os.makedirs("logs", exist_ok=True)
LOG_FILE = os.path.join("logs", "daily_sirene_delta.log")
MARKER_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".daily_sirene_delta_last_run")

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


def supabase_upsert_headers(return_rep: bool = False) -> Dict[str, str]:
    prefer = "resolution=merge-duplicates,return=minimal"
    if return_rep:
        prefer = "resolution=merge-duplicates,return=representation"
    return {
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def supabase_ignore_duplicate_headers() -> Dict[str, str]:
    """Pour les leads : ne pas écraser une ligne existante en cas de conflit SIREN."""
    return {
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=ignore-duplicates,return=representation",
    }


def is_excluded_brand(nom: str) -> bool:
    n = normaliser_nom(nom)
    for brand in EXCLUDED_BRANDS:
        if normaliser_nom(brand) in n:
            return True
    return False


def department_from_cp(cp: str) -> str:
    if not cp or len(cp) < 2:
        return ""
    if cp[:2] in ("97", "98") and len(cp) >= 3:
        return cp[:3]
    return cp[:2]


def zone_from_department(dep: str) -> Optional[str]:
    for zone, deps in ZONES.items():
        if dep in deps:
            return zone
    return None


def region_from_department(dep: str) -> str:
    return DEPARTEMENT_TO_REGION.get(dep, zone_from_department(dep) or "Autre")


def forme_juridique_from_code(code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    s = str(code)
    return FORME_JURIDIQUE_MAP.get(s, f"Code {s}")


def effectif_from_code(code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    return EFFECTIF_MAP.get(str(code))


def parse_adresse(adresse: Dict[str, Any]) -> str:
    return " ".join(filter(None, [
        adresse.get("numeroVoieEtablissement", ""),
        adresse.get("typeVoieEtablissement", ""),
        adresse.get("libelleVoieEtablissement", ""),
    ])).strip()


def parse_etablissement(e: Dict[str, Any]) -> Dict[str, Any]:
    adresse = e.get("adresseEtablissement", {}) or {}
    periodes = e.get("periodesEtablissement", []) or [{}]
    periode = periodes[0] if periodes else {}
    unite = e.get("uniteLegale", {}) or {}

    cp = adresse.get("codePostalEtablissement", "")
    dep = department_from_cp(cp)
    zone = zone_from_department(dep)

    return {
        "siren": e.get("siren", ""),
        "siret": e.get("siret", ""),
        "nom": (
            periode.get("enseigne1Etablissement")
            or unite.get("denominationUniteLegale")
            or f"{unite.get('prenomUsuelUniteLegale', '')} {unite.get('nomUniteLegale', '')}".strip()
            or "Inconnu"
        ),
        "nom_legal": unite.get("denominationUniteLegale") or None,
        "code_naf": periode.get("activitePrincipaleEtablissement", ""),
        "ville": adresse.get("libelleCommuneEtablissement", ""),
        "code_postal": cp,
        "adresse": parse_adresse(adresse),
        "etat_administratif": periode.get("etatAdministratifEtablissement", ""),
        "date_creation": e.get("dateCreationEtablissement", ""),
        "date_dernier_traitement": periode.get("dateDernierTraitementEtablissement", ""),
        "date_fermeture": periode.get("dateFermetureEtablissement", ""),
        "est_siege": e.get("etablissementSiege") is True,
        "zone": zone,
        "departement": dep,
        "unite_date_creation": unite.get("dateCreationUniteLegale"),
        "unite_categorie_juridique": (str(v) if (v := unite.get("categorieJuridiqueUniteLegale")) is not None else None),
        "unite_tranche_effectif": (str(v) if (v := unite.get("trancheEffectifsUniteLegale")) is not None else None),
        "unite_prenom": unite.get("prenomUsuelUniteLegale"),
        "unite_nom": unite.get("nomUniteLegale"),
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
        return f"periode({naf_filter} AND etatAdministratifEtablissement:F AND dateDernierTraitementEtablissement:[{date_from} TO {date_to}])"
    else:
        raise ValueError(f"Mode inconnu : {mode}")


def fetch_delta(query: str, mode_label: str) -> List[Dict[str, Any]]:
    """Interroge l'API Sirene avec un curseur et retourne les établissements trouvés."""
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


def group_etabs_by_siren(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        siren = r.get("siren")
        if siren:
            grouped.setdefault(siren, []).append(r)
    return grouped


def pick_lead_etab(etabs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Choisit l'établissement représentatif du lead : siège en zone prioritaire, sinon premier actif."""
    actifs = [e for e in etabs if e.get("etat_administratif") != "F"]
    if not actifs:
        return etabs[0] if etabs else None
    # Siège en zone cible
    for e in actifs:
        if e.get("est_siege") and e.get("zone"):
            return e
    # Premier actif en zone
    for e in actifs:
        if e.get("zone"):
            return e
    # Siège hors zone
    for e in actifs:
        if e.get("est_siege"):
            return e
    return actifs[0]


def siren_passes_filters(etabs: List[Dict[str, Any]], book: List[str]) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Vérifie si le SIREN a au moins un établissement actif dans une zone cible et non exclu."""
    for e in etabs:
        if e.get("etat_administratif") == "F":
            continue
        if not e.get("zone"):
            continue
        nom = e.get("nom", "")
        if is_excluded_brand(nom):
            continue
        if est_dans_bob(nom, book)[0]:
            continue
        return True, e
    return False, None


def filter_etabs_for_upsert(etabs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Garde les établissements actifs situés dans les zones cibles."""
    return [e for e in etabs if e.get("etat_administratif") != "F" and e.get("zone")]


def build_lead_row(siren: str, etabs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Construit une ligne lead à insérer pour un nouveau SIREN."""
    actifs = [e for e in etabs if e.get("etat_administratif") != "F"]
    if not actifs:
        return None

    e = pick_lead_etab(actifs)
    if not e or not e.get("zone"):
        return None

    nom = e.get("nom") or "Inconnu"
    nom_legal = e.get("nom_legal")
    row: Dict[str, Any] = {
        "siren": siren,
        "nom": nom,
        "ville": e.get("ville", ""),
        "code_postal": e.get("code_postal", ""),
        "zone": e.get("zone", ""),
        "code_naf": e.get("code_naf", ""),
        "statut": "nouveau",
        "nb_etablissements": len(actifs),
        "score": 0,
        "score_total": 0,
        "score_ca": 0,
        "score_sites": 0,
        "score_croissance": 0,
        "score_contact": 0,
        "score_intention": 0,
        "score_chaine": 0,
        "enriched_pappers": False,
        "enriched_google": False,
        "enriched_at": datetime.now().isoformat(),
    }

    if nom_legal and nom_legal != nom:
        row["nom_legal"] = nom_legal

    date_creation = e.get("unite_date_creation") or e.get("date_creation")
    if date_creation:
        row["date_creation"] = date_creation

    if e.get("unite_categorie_juridique"):
        fj = forme_juridique_from_code(e.get("unite_categorie_juridique"))
        if fj:
            row["forme_juridique"] = fj

    if e.get("unite_tranche_effectif"):
        eff = effectif_from_code(e.get("unite_tranche_effectif"))
        if eff:
            row["effectif"] = eff

    if e.get("unite_prenom") or e.get("unite_nom"):
        row["dirigeant_prenom"] = e.get("unite_prenom") or None
        row["dirigeant_nom"] = e.get("unite_nom") or None

    return row


def fetch_existing_lead_ids(sirens: List[str]) -> Dict[str, int]:
    """Récupère les lead_id déjà présents par SIREN."""
    existing: Dict[str, int] = {}
    if not sirens:
        return existing

    for i in range(0, len(sirens), 100):
        batch = sirens[i : i + 100]
        siren_filter = ",".join(batch)
        try:
            resp = requests.get(
                f"{SUPABASE_URL}/rest/v1/leads",
                params={
                    "select": "id,siren",
                    "siren": f"in.({siren_filter})",
                    "limit": 100,
                },
                headers=supabase_read_headers(),
                timeout=30,
            )
            if resp.status_code == 200:
                for row in resp.json():
                    existing[row.get("siren", "")] = row.get("id")
            else:
                log(f"  Erreur vérification Supabase HTTP {resp.status_code} : {resp.text[:200]}")
        except Exception as e:
            log(f"  Erreur vérification Supabase : {e}")

    return existing


def normalize_row_keys(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """PostgREST exige que toutes les lignes d'un batch aient les mêmes clés."""
    if not rows:
        return rows
    all_keys = set()
    for r in rows:
        all_keys.update(r.keys())
    for r in rows:
        for k in all_keys:
            if k not in r:
                r[k] = None
    return rows


def insert_new_leads(lead_rows: List[Dict[str, Any]]) -> Dict[str, int]:
    """Insère les nouveaux leads avec on_conflict=siren et retourne siren->id."""
    siren_to_id: Dict[str, int] = {}
    if not lead_rows:
        return siren_to_id

    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/leads?on_conflict=siren"
    headers = supabase_ignore_duplicate_headers()
    lead_rows = normalize_row_keys(lead_rows)
    total_batches = (len(lead_rows) + LEAD_UPSERT_BATCH_SIZE - 1) // LEAD_UPSERT_BATCH_SIZE

    for i in range(0, len(lead_rows), LEAD_UPSERT_BATCH_SIZE):
        batch = normalize_row_keys(lead_rows[i : i + LEAD_UPSERT_BATCH_SIZE])
        batch_num = i // LEAD_UPSERT_BATCH_SIZE + 1
        try:
            resp = requests.post(url, json=batch, headers=headers, timeout=60)
            if resp.status_code in (200, 201):
                for row in resp.json():
                    siren = row.get("siren")
                    lid = row.get("id")
                    if siren and lid:
                        siren_to_id[siren] = lid
                log(f"  Leads lot {batch_num}/{total_batches} : {len(resp.json())} insérés/récupérés")
            else:
                log(f"  Leads lot {batch_num}/{total_batches} : échec HTTP {resp.status_code} — {resp.text[:200]}")
        except Exception as e:
            log(f"  Leads lot {batch_num}/{total_batches} : erreur réseau — {e}")

    return siren_to_id


def upsert_etablissements(etab_rows: List[Dict[str, Any]]) -> Tuple[int, int]:
    """Upsert les établissements actifs par lots de 10."""
    ok = 0
    ko = 0
    if not etab_rows:
        return ok, ko

    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/etablissements?on_conflict=siret"
    headers = supabase_upsert_headers()
    total_batches = (len(etab_rows) + ETAB_UPSERT_BATCH_SIZE - 1) // ETAB_UPSERT_BATCH_SIZE

    for i in range(0, len(etab_rows), ETAB_UPSERT_BATCH_SIZE):
        batch = etab_rows[i : i + ETAB_UPSERT_BATCH_SIZE]
        batch_num = i // ETAB_UPSERT_BATCH_SIZE + 1
        try:
            resp = requests.post(url, json=batch, headers=headers, timeout=60)
            if resp.status_code in (200, 201):
                ok += len(batch)
                log(f"  Etab lot {batch_num}/{total_batches} : {len(batch)} upsertés")
            else:
                ko += len(batch)
                log(f"  Etab lot {batch_num}/{total_batches} : échec HTTP {resp.status_code} — {resp.text[:200]}")
        except Exception as e:
            ko += len(batch)
            log(f"  Etab lot {batch_num}/{total_batches} : erreur réseau — {e}")

    return ok, ko


def delete_closed_etablissements(sirets: List[str]) -> Tuple[int, int]:
    """Supprime les établissements fermés par lots de sirets."""
    ok = 0
    ko = 0
    if not sirets:
        return ok, ko

    for i in range(0, len(sirets), CLOSED_DELETE_BATCH_SIZE):
        batch = sirets[i : i + CLOSED_DELETE_BATCH_SIZE]
        siret_filter = ",".join(batch)
        try:
            resp = requests.delete(
                f"{SUPABASE_URL.rstrip('/')}/rest/v1/etablissements?siret=in.({siret_filter})",
                headers=supabase_write_headers(),
                timeout=30,
            )
            if resp.status_code in (200, 204):
                ok += len(batch)
            else:
                ko += len(batch)
                log(f"  Échec suppression fermés lot {i//CLOSED_DELETE_BATCH_SIZE+1} : HTTP {resp.status_code}")
        except Exception as e:
            ko += len(batch)
            log(f"  Erreur suppression fermés lot {i//CLOSED_DELETE_BATCH_SIZE+1} : {e}")

    return ok, ko


def refresh_lead_aggregates(lead_ids: List[int]) -> bool:
    """Appelle la fonction RPC refresh_lead_aggregates par paquets."""
    if not lead_ids:
        return True

    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/rpc/refresh_lead_aggregates"
    headers = {**supabase_write_headers(), "Content-Type": "application/json"}
    ok = True

    for i in range(0, len(lead_ids), 100):
        batch = lead_ids[i : i + 100]
        try:
            resp = requests.post(url, json={"p_lead_ids": batch}, headers=headers, timeout=60)
            if resp.status_code not in (200, 204):
                log(f"  Échec refresh_lead_aggregates lot {i//100+1} : HTTP {resp.status_code} — {resp.text[:200]}")
                ok = False
            else:
                log(f"  refresh_lead_aggregates lot {i//100+1} : {len(batch)} leads")
        except Exception as e:
            log(f"  Erreur refresh_lead_aggregates lot {i//100+1} : {e}")
            ok = False

    return ok


def recompute_scores(lead_ids: List[int]) -> Tuple[int, int]:
    """Recalcule les scores pour les leads donnés et met à jour par lots de 50."""
    ok = 0
    ko = 0
    if not lead_ids:
        return ok, ko

    # Récupérer les données fraîches après aggregation
    leads_to_score: List[Dict[str, Any]] = []
    for i in range(0, len(lead_ids), 100):
        batch = lead_ids[i : i + 100]
        id_filter = ",".join(str(lid) for lid in batch)
        try:
            resp = requests.get(
                f"{SUPABASE_URL}/rest/v1/leads",
                params={
                    "select": "id,siren,nb_etablissements,derniere_ouverture,sites_ouverts_12m,chiffre_affaires,croissance_ca,telephone,site_web,email,nb_tenders,nb_tender_notices,is_chaine",
                    "id": f"in.({id_filter})",
                    "limit": 100,
                },
                headers=supabase_read_headers(),
                timeout=30,
            )
            if resp.status_code == 200:
                leads_to_score.extend(resp.json())
            else:
                log(f"  Échec récupération scores lot {i//100+1} : HTTP {resp.status_code}")
                ko += len(batch)
        except Exception as e:
            log(f"  Erreur récupération scores lot {i//100+1} : {e}")
            ko += len(batch)

    updates = []
    for lead in leads_to_score:
        sr = compute_score(lead)
        updates.append({
            "siren": lead["siren"],
            "score": sr["score_total"],
            "score_total": sr["score_total"],
            "score_ca": sr["score_ca"],
            "score_sites": sr["score_sites"],
            "score_croissance": sr["score_croissance"],
            "score_contact": sr["score_contact"],
            "score_intention": sr["score_intention"],
            "score_chaine": sr["score_chaine"],
        })

    if not updates:
        return ok, ko

    total = len(updates)
    total_batches = (total + LEAD_UPDATE_BATCH_SIZE - 1) // LEAD_UPDATE_BATCH_SIZE
    for i in range(0, total, LEAD_UPDATE_BATCH_SIZE):
        batch = updates[i : i + LEAD_UPDATE_BATCH_SIZE]
        batch_num = i // LEAD_UPDATE_BATCH_SIZE + 1
        batch_ok = 0
        batch_ko = 0
        for upd in batch:
            try:
                resp = requests.patch(
                    f"{SUPABASE_URL.rstrip('/')}/rest/v1/leads?siren=eq.{upd['siren']}",
                    headers=supabase_write_headers(),
                    json={
                        "score": upd["score"],
                        "score_total": upd["score_total"],
                        "score_ca": upd["score_ca"],
                        "score_sites": upd["score_sites"],
                        "score_croissance": upd["score_croissance"],
                        "score_contact": upd["score_contact"],
                        "score_intention": upd["score_intention"],
                        "score_chaine": upd["score_chaine"],
                    },
                    timeout=30,
                )
                if resp.status_code in (200, 204):
                    batch_ok += 1
                else:
                    batch_ko += 1
                    log(f"  Échec score {upd['siren']} : HTTP {resp.status_code}")
            except Exception as e:
                batch_ko += 1
                log(f"  Erreur score {upd['siren']} : {e}")
        ok += batch_ok
        ko += batch_ko
        log(f"  Scores lot {batch_num}/{total_batches} : {batch_ok} mis à jour, {batch_ko} échecs")

    return ok, ko


def compute_score(lead: Dict[str, Any]) -> Dict[str, int]:
    """Portage Python du scoring canonical (sql/recalc_scores.sql)."""
    ca = lead.get("chiffre_affaires")
    has_ca = ca is not None and ca > 0
    g = lead.get("croissance_ca")
    has_ca_growth = g is not None
    nb_etabs = lead.get("nb_etablissements") or 1
    sites_ouverts = lead.get("sites_ouverts_12m") or 0
    derniere_ouverture = lead.get("derniere_ouverture")

    within_6_months = False
    within_12_months = False
    if derniere_ouverture:
        try:
            d = datetime.fromisoformat(str(derniere_ouverture).replace("Z", "+00:00"))
            now = datetime.now(d.tzinfo) if d.tzinfo else datetime.now()
            within_6_months = d >= now - timedelta(days=180)
            within_12_months = d >= now - timedelta(days=365)
        except Exception:
            pass

    # Axe CA (max 30)
    score_ca = 0
    if has_ca:
        if ca >= 5_000_000:
            score_ca = 30
        elif ca >= 2_000_000:
            score_ca = 25
        elif ca >= 1_000_000:
            score_ca = 20
        elif ca >= 500_000:
            score_ca = 15
        elif ca >= 100_000:
            score_ca = 10
        else:
            score_ca = 5

    # Axe Sites (max 35, redistribué à 60 si CA absent)
    score_sites_raw = 0
    if nb_etabs >= 10:
        score_sites_raw = 35
    elif nb_etabs >= 5:
        score_sites_raw = 30
    elif nb_etabs >= 3:
        score_sites_raw = 20
    elif nb_etabs >= 2:
        score_sites_raw = 12

    # Axe Croissance (max 30)
    score_ca_growth = 0
    if has_ca_growth:
        if g >= 30:
            score_ca_growth = 15
        elif g >= 15:
            score_ca_growth = 12
        elif g >= 5:
            score_ca_growth = 8
        elif g >= 0:
            score_ca_growth = 4

    score_ouvertures = 0
    if sites_ouverts >= 3:
        score_ouvertures = 10
    elif sites_ouverts >= 2:
        score_ouvertures = 6
    elif sites_ouverts >= 1:
        score_ouvertures = 3 if within_6_months else 0

    score_combo = 0
    if derniere_ouverture:
        if nb_etabs >= 3 and within_6_months:
            score_combo = 5
        elif nb_etabs >= 2 and within_12_months:
            score_combo = 2

    score_croissance = score_ca_growth + score_ouvertures + score_combo

    if not has_ca:
        score_sites = round(score_sites_raw / 35 * 60)
    else:
        score_sites = score_sites_raw

    # Axe Contact (max 25)
    score_contact = 0
    telephone = lead.get("telephone") or ""
    site_web = lead.get("site_web") or ""
    email = lead.get("email") or ""
    if telephone:
        score_contact += 10
    if site_web:
        score_contact += 8
    if email:
        score_contact += 7

    # Axe Intention (max 25)
    score_intention = 0
    if has_ca_growth:
        if g >= 30:
            score_intention += 10
        elif g >= 15:
            score_intention += 7
        elif g >= 5:
            score_intention += 4
    if sites_ouverts >= 3:
        score_intention += 8
    elif sites_ouverts >= 1:
        score_intention += 4
    if (lead.get("nb_tenders") or 0) >= 1:
        score_intention += 5
    if (lead.get("nb_tender_notices") or 0) >= 1:
        score_intention += 2

    # Axe Chaîne / Franchise (max 20)
    score_chaine = 0
    if nb_etabs >= 10:
        score_chaine = 15
    elif nb_etabs >= 5:
        score_chaine = 12
    elif nb_etabs >= 3:
        score_chaine = 8
    elif nb_etabs >= 2:
        score_chaine = 4
    if lead.get("is_chaine"):
        score_chaine += 5

    # Score total pondéré (normalisé sur 100, aligné avec sql/recalc_scores.sql)
    score_total = round(
        (
            score_ca / 30.0 * 0.30
            + score_sites / 35.0 * 0.25
            + score_croissance / 30.0 * 0.20
            + score_contact / 25.0 * 0.10
            + score_intention / 25.0 * 0.10
            + score_chaine / 20.0 * 0.05
        ) * 100
    )

    return {
        "score": score_total,
        "score_total": score_total,
        "score_ca": score_ca,
        "score_sites": score_sites,
        "score_croissance": score_croissance,
        "score_contact": score_contact,
        "score_intention": score_intention,
        "score_chaine": score_chaine,
    }


def _supabase_get_state(key: str) -> Optional[str]:
    try:
        url = f"{SUPABASE_URL}/rest/v1/scheduler_state?key=eq.{key}&select=value"
        resp = requests.get(url, headers={
            "apikey": SUPABASE_API_KEY,
            "Authorization": f"Bearer {SUPABASE_API_KEY}",
        }, timeout=10)
        if resp.status_code == 200:
            rows = resp.json()
            if rows:
                return rows[0]["value"]
    except Exception:
        pass
    return None


def _supabase_set_state(key: str, value: str):
    try:
        url = f"{SUPABASE_URL}/rest/v1/scheduler_state"
        requests.post(url, headers={
            "apikey": SUPABASE_API_KEY,
            "Authorization": f"Bearer {SUPABASE_API_KEY}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        }, json={"key": key, "value": value}, timeout=10)
    except Exception:
        pass


def load_last_run_date() -> str:
    remote = _supabase_get_state("daily_sirene_delta_last_run")
    if remote:
        return remote
    if os.path.exists(MARKER_FILE):
        with open(MARKER_FILE, "r") as f:
            return f.read().strip()
    yesterday = datetime.now() - timedelta(days=1)
    return yesterday.strftime("%Y-%m-%d")


def save_last_run_date(date_str: str):
    _supabase_set_state("daily_sirene_delta_last_run", date_str)
    try:
        with open(MARKER_FILE, "w") as f:
            f.write(date_str)
    except OSError:
        pass


def main():
    log("=" * 60)
    log("Daily Sirene Delta — démarrage")
    log("=" * 60)

    if not INSEE_API_KEY:
        log("INSEE_API_KEY manquant. Arrêt.")
        sys.exit(1)
    if not SUPABASE_URL or not SUPABASE_API_KEY:
        log("SUPABASE_URL/SUPABASE_API_KEY manquants. Arrêt.")
        sys.exit(1)

    today = datetime.now().strftime("%Y-%m-%d")
    date_from = load_last_run_date()
    date_to = today

    if date_from >= date_to:
        log(f"Dernière exécution ({date_from}) est déjà aujourd'hui. Rien à faire.")
        return

    log(f"Fenêtre de recherche : {date_from} TO {date_to}")

    book = charger_book()
    log(f"Book of business chargé : {len(book)} noms")

    # ─── 1. Récupérer les deltas INSEE ───
    creations = fetch_delta(build_query_date_window(date_from, date_to, "creation"), "nouvelles créations")
    time.sleep(REQUEST_DELAY)

    updates = fetch_delta(build_query_date_window(date_from, date_to, "update"), "mises à jour")
    time.sleep(REQUEST_DELAY)

    fermetures = fetch_delta(build_query_date_window(date_from, date_to, "fermeture"), "fermetures")

    all_rows = creations + updates + fermetures
    log(f"\nTotal brut récupéré : {len(all_rows)} (créations={len(creations)}, maj={len(updates)}, fermetures={len(fermetures)})")

    # ─── 2. Grouper par SIREN et filtrer ───
    by_siren = group_etabs_by_siren(all_rows)
    stats = {
        "total_sirens": len(by_siren),
        "hors_zone": 0,
        "exclu_marque": 0,
        "exclu_bob": 0,
        "gardes": 0,
        "fermetures": 0,
    }

    processed_sirens: Set[str] = set()
    new_siren_candidates: Set[str] = set()
    siren_to_etabs: Dict[str, List[Dict[str, Any]]] = {}

    for siren, etabs in by_siren.items():
        passes, _ = siren_passes_filters(etabs, book)
        if not passes:
            # Déterminer la raison principale pour les stats
            actifs_zone = [e for e in etabs if e.get("etat_administratif") != "F" and e.get("zone")]
            if not actifs_zone:
                stats["hors_zone"] += 1
            else:
                # Vérifie marque puis BOB
                marque_exclue = any(is_excluded_brand(e.get("nom", "")) for e in actifs_zone)
                if marque_exclue:
                    stats["exclu_marque"] += 1
                elif any(est_dans_bob(e.get("nom", ""), book)[0] for e in actifs_zone):
                    stats["exclu_bob"] += 1
                else:
                    stats["hors_zone"] += 1
            continue

        processed_sirens.add(siren)
        siren_to_etabs[siren] = etabs
        fermetures_count = len([e for e in etabs if e.get("etat_administratif") == "F"])
        stats["fermetures"] += fermetures_count
        stats["gardes"] += 1

    # ─── 3. Récupérer les leads existants ───
    existing_lead_ids = fetch_existing_lead_ids(list(processed_sirens))
    log(f"  SIRENs déjà en base : {len(existing_lead_ids)} / {len(processed_sirens)}")

    # ─── 4. Construire et insérer les nouveaux leads ───
    new_lead_rows = []
    for siren in processed_sirens:
        if siren in existing_lead_ids:
            continue
        row = build_lead_row(siren, siren_to_etabs[siren])
        if row:
            new_lead_rows.append(row)
        else:
            log(f"  Impossible de construire le lead {siren} (aucun établissement actif)")

    new_siren_ids = insert_new_leads(new_lead_rows)
    log(f"  Nouveaux leads insérés : {len(new_siren_ids)}")

    # ─── 5. Mapper SIREN -> lead_id ───
    siren_to_lead_id: Dict[str, int] = {}
    for siren, lead_id in existing_lead_ids.items():
        siren_to_lead_id[siren] = lead_id
    for siren, lead_id in new_siren_ids.items():
        siren_to_lead_id[siren] = lead_id

    # ─── 6. Supprimer les établissements fermés ───
    closed_sirets = []
    for siren in processed_sirens:
        if siren not in siren_to_lead_id:
            continue
        for e in siren_to_etabs[siren]:
            if e.get("etat_administratif") == "F" and e.get("siret"):
                closed_sirets.append(e["siret"])

    ok_del, ko_del = delete_closed_etablissements(closed_sirets)
    log(f"  Établissements fermés supprimés : {ok_del} (échecs : {ko_del})")

    # ─── 7. Upsert les établissements actifs ───
    etab_rows = []
    for siren in processed_sirens:
        lead_id = siren_to_lead_id.get(siren)
        if not lead_id:
            continue
        for e in filter_etabs_for_upsert(siren_to_etabs[siren]):
            etab_rows.append({
                "lead_id": lead_id,
                "siren": siren,
                "siret": e.get("siret"),
                "nom": e.get("nom") or "Inconnu",
                "adresse": e.get("adresse") or None,
                "ville": e.get("ville", ""),
                "code_postal": e.get("code_postal", ""),
                "date_creation": e.get("date_creation") or None,
                "code_naf": e.get("code_naf") or None,
                "est_siege": e.get("est_siege") or False,
            })

    ok_upsert, ko_upsert = upsert_etablissements(etab_rows)
    log(f"  Établissements actifs upsertés : {ok_upsert} (échecs : {ko_upsert})")

    # ─── 8. Rafraîchir les agrégats lead ───
    affected_lead_ids = list(set(siren_to_lead_id.values()))
    log(f"  Leads affectés : {len(affected_lead_ids)}")
    refresh_ok = refresh_lead_aggregates(affected_lead_ids)

    # ─── 9. Recalculer les scores ───
    ok_score, ko_score = recompute_scores(affected_lead_ids)
    log(f"  Scores mis à jour : {ok_score} (échecs : {ko_score})")

    log("\n--- Résultat ---")
    log(f"  SIRENs uniques : {stats['total_sirens']}")
    log(f"  SIRENs retenus : {stats['gardes']} (hors zone={stats['hors_zone']}, marque={stats['exclu_marque']}, BOB={stats['exclu_bob']})")
    log(f"  Fermetures détectées : {stats['fermetures']}")
    log(f"  Nouveaux leads : {len(new_siren_ids)} | Existants : {len(existing_lead_ids)}")
    log(f"  Etablissements : upsert={ok_upsert}, fermés supprimés={ok_del}")
    log(f"  Refresh agrégats : {'OK' if refresh_ok else 'ÉCHEC'}")
    log(f"  Scores : mis à jour={ok_score}, échecs={ko_score}")

    if not refresh_ok or ko_score > 0 or ko_upsert > 0 or ko_del > 0:
        log("  Des erreurs ont été détectées ; la date de dernier run n'est PAS sauvegardée.")
        sys.exit(1)

    save_last_run_date(today)
    log(f"\nProchain run à partir de : {today}")
    log("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"ERREUR FATALE : {e}")
        sys.exit(1)
