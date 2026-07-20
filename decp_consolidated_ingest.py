"""
Ingestion du DECP consolidé (data.gouv.fr) dans Supabase.

Télécharge le fichier JSON mensuel le plus récent, filtre les marchés de restauration
(codes CPV ou mots-clés), et upserte les marchés attribués dans les tables `tenders`,
`tender_awards` et `tender_locations`. Effectue un matching SIREN basique sur la table
`leads` et calcule un score d'opportunité.

Usage:
    python decp_consolidated_ingest.py

Variables d'environnement (optionnel):
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY
    DECP_MONTH (ex: 2026-07 pour forcer un mois précis)
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from typing import Any

import requests

SUPABASE_URL = os.environ.get(
    "SUPABASE_URL", "https://hxjryfaakdpwfgseirik.supabase.co"
)
SUPABASE_KEY = os.environ.get(
    "SUPABASE_SERVICE_ROLE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imh4anJ5ZmFha2Rwd2Znc2VpcmlrIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MjkwMzgwMCwiZXhwIjoyMDk4NDc5ODAwfQ.gGba1EWAucnG7kaI2E__-lSWj1yAQjyEp2LpltFiKKw",
)

DECP_DATASET_SLUG = "donnees-essentielles-de-la-commande-publique-fichiers-consolides"
DATASET_API_URL = f"https://www.data.gouv.fr/api/1/datasets/{DECP_DATASET_SLUG}/"

# Codes CPV restauration (division / famille)
RESTAURATION_CPV_PREFIXES = {
    "15",  # denrées alimentaires
    "55",  # hôtellerie, restauration
    "158",  # produits alimentaires divers
    "553",  # denrées alimentaires, boissons, tabac
    "555",  # services de restauration
}

CPU_KEYWORDS = [
    "restauration collective",
    "cantine",
    "cantine scolaire",
    "cantine d'entreprise",
    "cuisine centrale",
    "collective",
    "hopital",
    "hôpital",
    "ehpad",
    "maison de retraite",
    "ecole",
    "école",
    "université",
    "universite",
    "entreprise",
    "administration",
    "collectivité",
    "collectivite",
    "collège",
    "lycée",
    "self",
    "buffet",
    "plateau repas",
]

DK_KEYWORDS = [
    "traiteur",
    "traiteurs",
    "livraison",
    "dark kitchen",
    "cloud kitchen",
    "ghost kitchen",
    "preparation de repas",
    "préparation de repas",
    "plateforme",
    "commande en ligne",
    "delivery",
    "fourniture de repas",
    "prestation de repas",
    "service de repas",
]

BATCH_UPSERT_SIZE = 200
REQUEST_TIMEOUT = 60


def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)


def supabase_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


def supabase_upsert_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=representation",
    }


def get_latest_monthly_resource_url():
    """Récupère l'URL du fichier JSON mensuel le plus récent."""
    log("Récupération des métadonnées data.gouv.fr...")
    resp = requests.get(DATASET_API_URL, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    resources = data.get("resources", [])
    monthly = []
    for r in resources:
        title = r.get("title", "")
        fmt = r.get("format", "").lower()
        if fmt != "json":
            continue
        m = re.match(r"decp-(\d{4})-(\d{2})\.json", title)
        if m:
            monthly.append((f"{m.group(1)}-{m.group(2)}", r))

    if not monthly:
        raise RuntimeError("Aucune ressource mensuelle DECP JSON trouvée")

    monthly.sort(key=lambda x: x[0], reverse=True)
    month, resource = monthly[0]
    url = resource.get("url") or resource.get("latest")
    if not url:
        url = f"https://www.data.gouv.fr/api/1/datasets/r/{resource['id']}"

    log(f"Ressource sélectionnée : {resource.get('title')} ({month})")
    return month, url


def resolve_download_url(url):
    """Résout la redirection data.gouv.fr vers l'URL static."""
    if url.startswith("https://www.data.gouv.fr/api/1/datasets/r/"):
        resp = requests.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=False)
        if resp.status_code in (301, 302, 307, 308) and resp.headers.get("Location"):
            return resp.headers["Location"]
        resp.raise_for_status()
        return resp.json().get("url", url)
    return url


def derive_opportunity_type(cpv: str | None, objet: str) -> str:
    """Classification simple DK / CPU / both / none."""
    cpv_clean = (cpv or "").replace("-", "").replace(" ", "")
    cpv_prefix = cpv_clean[:3] if len(cpv_clean) >= 3 else ""
    cpv_division = cpv_clean[:2] if len(cpv_clean) >= 2 else ""
    obj = (objet or "").lower()

    is_cpu_by_cpv = cpv_prefix in {"150", "555", "553"} or cpv_division == "55"
    is_dk_by_cpv = cpv_prefix in {"158", "553"} or cpv_division == "15"

    is_cpu_by_text = any(k.lower() in obj for k in CPU_KEYWORDS)
    is_dk_by_text = any(k.lower() in obj for k in DK_KEYWORDS)

    cpu_signals = (1 if is_cpu_by_cpv else 0) + (1 if is_cpu_by_text else 0)
    dk_signals = (1 if is_dk_by_cpv else 0) + (1 if is_dk_by_text else 0)

    if cpu_signals > 0 and dk_signals > 0:
        return "both"
    if cpu_signals > 0:
        return "cpu"
    if dk_signals > 0:
        return "dark_kitchen"
    return "none"


def compute_score(opportunity_type: str, cpv: str | None, objet: str) -> int:
    """Score simplifié 0-100."""
    if opportunity_type == "none":
        return 0

    score = 0
    if opportunity_type in ("cpu", "both"):
        score += 20
    if opportunity_type == "dark_kitchen":
        score += 12

    obj = (objet or "").lower()
    strong_cpu = ["restauration collective", "cantine scolaire", "cuisine centrale", "ehpad", "hopital", "hôpital", "école", "université", "collège", "lycée"]
    strong_dk = ["dark kitchen", "cloud kitchen", "ghost kitchen", "traiteur", "livraison repas", "commande en ligne"]

    if any(t in obj for t in strong_cpu):
        score += 8
    if any(t in obj for t in strong_dk):
        score += 8

    score += 12  # géographie non évaluée ici

    # temporal : recent publication
    score += 10

    return min(score, 100)


def is_restaurant_record(record):
    """Détermine si un marché est lié à la restauration."""
    objet = (record.get("objet") or "").lower()
    cpv = (record.get("codeCPV") or "").replace("-", "").replace(" ", "")

    cpv_prefix = cpv[:3] if len(cpv) >= 3 else cpv[:2] if len(cpv) >= 2 else ""
    if cpv_prefix in RESTAURATION_CPV_PREFIXES:
        return True

    if any(k.lower() in objet for k in CPU_KEYWORDS + DK_KEYWORDS):
        return True

    return False


def extract_siren(siret: str | None) -> str | None:
    if not siret or len(siret) < 9:
        return None
    return siret[:9]


def load_leads_siren_map() -> dict[str, int]:
    """Charge les leads existants indexés par SIREN."""
    log("Chargement des leads depuis Supabase...")
    mapping = {}
    offset = 0
    page_size = 1000
    while True:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/leads",
            headers={**supabase_headers(), "Range": f"{offset}-{offset + page_size - 1}"},
            params={"select": "id,siren", "order": "id"},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code == 416:
            break
        rows = resp.json()
        if not rows:
            break
        for r in rows:
            if r.get("siren"):
                mapping[r["siren"]] = r["id"]
        if len(rows) < page_size:
            break
        offset += page_size
    log(f"{len(mapping)} leads chargés")
    return mapping


def normalize_tender(record, month: str) -> dict[str, Any]:
    """Normalise un marché DECP en objet `tender` compatible avec le schéma Supabase."""
    acheteur = record.get("acheteur", {}) or {}
    lieu = record.get("lieuExecution", {}) or {}

    acheteur_id = acheteur.get("id") if isinstance(acheteur, dict) else None
    acheteur_id_str = acheteur_id if isinstance(acheteur_id, str) else None

    montant = record.get("montant")
    if not isinstance(montant, (int, float)):
        montant = None

    duree = record.get("dureeMois")
    if not isinstance(duree, int):
        duree = None

    date_notification = record.get("dateNotification") or None
    date_fin = None
    if date_notification and duree:
        try:
            date_fin = (datetime.fromisoformat(date_notification) + timedelta(days=30 * duree)).strftime("%Y-%m-%d")
        except Exception:
            date_fin = None

    cpv = record.get("codeCPV") or None

    return {
        "source": "decp-consolidated",
        "source_id": f"decp-consolidated:{record.get('id')}:{month}",
        "objet": record.get("objet") or "Marché public",
        "acheteur_nom": None,
        "acheteur_siret": acheteur_id_str,
        "acheteur_code_postal": lieu.get("code") if isinstance(lieu, dict) and lieu.get("typeCode") == "Code postal" else None,
        "acheteur_ville": None,
        "montant": montant,
        "date_notification": date_notification,
        "duree_mois": duree,
        "date_fin_contrat": date_fin,
        "code_cpv": cpv,
        "cpv_libelle": None,
        "procedure": record.get("procedure") or None,
        "nature": record.get("nature") or None,
        "forme_prix": record.get("formePrix") or None,
        "offres_recues": record.get("offresRecues") if isinstance(record.get("offresRecues"), int) else None,
        "raw_data": record,
        "ingested_at": datetime.now().astimezone().isoformat(),
    }


def normalize_awards(record, tender_id: int, leads_map: dict) -> list[dict[str, Any]]:
    """Normalise les titulaires d'un marché en `tender_awards`."""
    titulaires = record.get("titulaires", []) or []
    awards = []
    for t in titulaires:
        if not isinstance(t, dict):
            continue
        titulaire = t.get("titulaire", t)
        if not isinstance(titulaire, dict):
            continue
        siret = titulaire.get("id") if isinstance(titulaire.get("id"), str) else None
        siren = extract_siren(siret)
        denomination = titulaire.get("denominationSociale") or None
        lead_id = leads_map.get(siren) if siren else None

        cpv = record.get("codeCPV") or None
        opportunity_type = derive_opportunity_type(cpv, record.get("objet", ""))
        score = compute_score(opportunity_type, cpv, record.get("objet", ""))

        awards.append({
            "tender_id": tender_id,
            "siret": siret,
            "siren": siren,
            "denomination_sociale": denomination,
            "montant": None,
            "est_sme": None,
            "est_pme": None,
            "lead_id": lead_id,
            "opportunity_type": opportunity_type,
            "opportunity_type_confidence": 0.5,
            "opportunity_score": score,
            "score_marche": 20 if opportunity_type in ("cpu", "both") else 12 if opportunity_type == "dark_kitchen" else 0,
            "score_adjudicataire": 0,
            "score_geographie": 12,
            "score_temporel": 10,
        })
    return awards


def normalize_locations(record, tender_id: int) -> list[dict[str, Any]]:
    """Normalise les lieux d'exécution."""
    lieu = record.get("lieuExecution", {}) or {}
    if not isinstance(lieu, dict):
        return []
    code = lieu.get("code")
    type_code = lieu.get("typeCode")
    if not code or not type_code:
        return []
    return [{
        "tender_id": tender_id,
        "type_code": type_code,
        "code": code,
        "nom": None,
    }]


def upsert_tenders(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Upserte des tenders et retourne les lignes avec leur id Supabase."""
    if not rows:
        return []

    url = f"{SUPABASE_URL}/rest/v1/tenders"
    resp = requests.post(
        url,
        headers=supabase_upsert_headers(),
        json=rows,
        params={"on_conflict": "source_id"},
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code not in (200, 201):
        log(f"ERREUR upsert tenders: {resp.status_code} {resp.text[:500]}")
        return []

    return resp.json()


def upsert_awards(rows: list[dict[str, Any]]):
    if not rows:
        return 0, 0

    url = f"{SUPABASE_URL}/rest/v1/tender_awards"
    resp = requests.post(
        url,
        headers=supabase_upsert_headers(),
        json=rows,
        params={"on_conflict": "tender_id, siret, siren, denomination_sociale"},
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code not in (200, 201):
        log(f"ERREUR upsert awards: {resp.status_code} {resp.text[:500]}")
        return 0, len(rows)

    returned = resp.json()
    inserted = sum(1 for r in returned if r.get("created_at") == r.get("updated_at"))
    updated = len(returned) - inserted
    return inserted, updated


def upsert_locations(rows: list[dict[str, Any]]):
    if not rows:
        return 0, 0

    url = f"{SUPABASE_URL}/rest/v1/tender_locations"
    resp = requests.post(
        url,
        headers=supabase_upsert_headers(),
        json=rows,
        params={"on_conflict": "tender_id, type_code, code"},
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code not in (200, 201):
        log(f"ERREUR upsert locations: {resp.status_code} {resp.text[:500]}")
        return 0, len(rows)

    returned = resp.json()
    inserted = sum(1 for r in returned if r.get("created_at") == r.get("updated_at"))
    updated = len(returned) - inserted
    return inserted, updated


def main():
    forced_month = os.environ.get("DECP_MONTH")
    if forced_month:
        month = forced_month
        url = f"https://www.data.gouv.fr/api/1/datasets/r/b7f37860-c2ce-428d-a03d-19ab28aaa4a2"  # fallback
    else:
        month, url = get_latest_monthly_resource_url()

    download_url = resolve_download_url(url)
    log(f"Téléchargement : {download_url}")

    t0 = time.time()
    with requests.get(download_url, stream=True, timeout=REQUEST_TIMEOUT) as resp:
        resp.raise_for_status()
        log("Lecture et parsing du fichier JSON...")
        data = resp.json()

    log(f"Fichier téléchargé et parsé en {time.time() - t0:.1f}s")

    marches = data.get("marches", {}).get("marche", []) or []
    if not isinstance(marches, list):
        log("Structure inattendue : marches.marche n'est pas une liste")
        sys.exit(1)

    log(f"Total de marchés dans le fichier : {len(marches)}")

    matches = [m for m in marches if is_restaurant_record(m)]
    log(f"Marchés restauration identifiés : {len(matches)}")

    # Déduplication par id de marché (le fichier DECP peut contenir des doublons / avenants).
    seen_ids = set()
    deduped_matches = []
    for m in matches:
        rid = m.get("id")
        if rid in seen_ids:
            continue
        seen_ids.add(rid)
        deduped_matches.append(m)
    matches = deduped_matches
    log(f"Marchés uniques après déduplication : {len(matches)}")

    leads_map = load_leads_siren_map()

    inserted_tenders = 0
    updated_tenders = 0
    inserted_awards = 0
    updated_awards = 0
    inserted_locations = 0
    updated_locations = 0

    total_batches = (len(matches) + BATCH_UPSERT_SIZE - 1) // BATCH_UPSERT_SIZE
    for i in range(0, len(matches), BATCH_UPSERT_SIZE):
        batch = matches[i : i + BATCH_UPSERT_SIZE]
        tender_rows = [normalize_tender(m, month) for m in batch]

        returned = upsert_tenders(tender_rows)
        if not returned:
            log(f"  Batch {i // BATCH_UPSERT_SIZE + 1}/{total_batches}: échec tenders")
            continue

        source_id_to_id = {r["source_id"]: r["id"] for r in returned}

        batch_inserted_tenders = 0
        batch_updated_tenders = 0
        for r in returned:
            if r.get("created_at") == r.get("updated_at"):
                batch_inserted_tenders += 1
            else:
                batch_updated_tenders += 1
        inserted_tenders += batch_inserted_tenders
        updated_tenders += batch_updated_tenders

        award_rows = []
        location_rows = []
        for original, tender_row in zip(batch, tender_rows):
            tender_id = source_id_to_id.get(tender_row["source_id"])
            if not tender_id:
                continue
            award_rows.extend(normalize_awards(original, tender_id, leads_map))
            location_rows.extend(normalize_locations(original, tender_id))

        ia, ua = upsert_awards(award_rows)
        inserted_awards += ia
        updated_awards += ua

        il, ul = upsert_locations(location_rows)
        inserted_locations += il
        updated_locations += ul

        log(
            f"  Batch {i // BATCH_UPSERT_SIZE + 1}/{total_batches}: "
            f"tenders +{batch_inserted_tenders}/{batch_updated_tenders}, "
            f"awards +{ia}/{ua}, "
            f"locations +{il}/{ul}"
        )

    log(
        "TERMINE: "
        f"tenders {inserted_tenders} inserts / {updated_tenders} updates, "
        f"awards {inserted_awards} inserts / {updated_awards} updates, "
        f"locations {inserted_locations} inserts / {updated_locations} updates"
    )


if __name__ == "__main__":
    main()
