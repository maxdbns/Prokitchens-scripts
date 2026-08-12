"""
Enrichissement des dirigeants via l'API INPI.

Cible : tous les leads ProKitchens (NAF 56.10C, 56.21Z, 56.29B) sur les zones
IDF, Lyon, Lille, Marseille, déjà enrichis INPI (financier) ou prioritaires,
et n'ayant pas encore de dirigeant.

Quota INPI : 10 000 requêtes/jour. Le script s'arrête automatiquement au quota.
"""

import os
import sys
import requests
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

# ─── Config ───
INPI_USERNAME = os.environ.get("INPI_USERNAME")
INPI_PASSWORD = os.environ.get("INPI_PASSWORD")
INPI_BASE_URL = "https://registre-national-entreprises.inpi.fr/api"

SUPABASE_URL = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_TABLE = os.environ.get("SUPABASE_TABLE", "leads")

DAILY_QUOTA = 9500
REQUEST_DELAY = 0.35
BATCH_SIZE = 1000
os.makedirs("logs", exist_ok=True)
LOG_FILE = os.path.join("logs", "inpi_enrich_dirigeants.log")

# NAF et zones cibles
NAFS_CIBLES = ["56.10C", "56.21Z", "56.29B"]
ZONES_DEPTS = {
    "75", "77", "78", "91", "92", "93", "94", "95",  # IDF
    "69",  # Lyon
    "59", "62",  # Lille
    "13", "83", "84",  # Marseille
}

ROLE_LABELS = {
    "53": "Président",
    "65": "Directeur général",
    "10": "Gérant",
    "11": "Co-gérant",
    "16": "Président du conseil d'administration",
    "17": "Administrateur",
    "30": "Directeur général délégué",
    "52": "Président directeur général",
    "71": "Représentant permanent",
}


def log(msg: str):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def supabase_headers() -> Dict[str, str]:
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


def inpi_login() -> str:
    resp = requests.post(
        f"{INPI_BASE_URL}/sso/login",
        json={"username": INPI_USERNAME, "password": INPI_PASSWORD},
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    log("Connecté à l'API INPI")
    return resp.json()["token"]


def fetch_leads(limit: int) -> List[Dict[str, Any]]:
    """
    Récupère les leads cibles :
    - NAF cible
    - département cible
    - pas de dirigeant déjà renseigné
    - pas d'échec récent INPI dirigeants (< 30 jours)
    """
    dept_or = ",".join(f"code_postal.like.{dep}*" for dep in sorted(ZONES_DEPTS))
    thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()

    # Syntaxe PostgREST : and=(or(dept1,dept2,...),code_naf.in.(...),dirigeant_nom.is.null,...)
    and_filter = (
        f"(or({dept_or}),"
        f"code_naf.in.({','.join(NAFS_CIBLES)}),"
        f"dirigeant_nom.is.null,"
        f"or(inpi_dirigeants_failed.is.null,inpi_dirigeants_failed.lt.{thirty_days_ago}))"
    )

    params = {
        "select": "siren,nom,ville,code_postal",
        "and": and_filter,
        "limit": limit,
        "order": "score.desc.nullslast",
    }

    try:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}",
            params=params,
            headers=supabase_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log(f"Erreur récupération leads : {e}")
        return []


def extract_dirigeant(data: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """Extrait le premier dirigeant individuel de la réponse INPI."""
    content = data.get("formality", {}).get("content", {})

    # Personne morale
    pm = content.get("personneMorale", {})
    pouvoirs = pm.get("composition", {}).get("pouvoirs", [])

    # Personne physique
    pp = content.get("personnePhysique", {})
    if not pouvoirs and pp:
        etablissement = pp.get("etablissementPrincipal", {})
        nom = pp.get("nom")
        prenoms = pp.get("prenoms", [])
        if nom and prenoms:
            return {
                "dirigeant_nom": nom.title(),
                "dirigeant_prenom": prenoms[0].title(),
                "dirigeant_role": "Entrepreneur individuel",
            }

    for pouvoir in pouvoirs:
        individu = pouvoir.get("individu", {})
        desc = individu.get("descriptionPersonne", {})
        nom = desc.get("nom")
        prenoms = desc.get("prenoms", [])
        role_code = pouvoir.get("roleEntreprise", "")

        if nom and prenoms:
            return {
                "dirigeant_nom": nom.title(),
                "dirigeant_prenom": prenoms[0].title(),
                "dirigeant_role": ROLE_LABELS.get(role_code, role_code),
            }

    return None


def get_dirigeant(siren: str, headers: Dict[str, str]) -> Optional[Dict[str, str]]:
    """
    Récupère le dirigeant pour un SIREN. Retourne None si non trouvé.
    Retourne la string 'REAUTH' si le token a expiré.
    """
    try:
        resp = requests.get(
            f"{INPI_BASE_URL}/companies/{siren}",
            headers=headers,
            timeout=30,
        )
    except requests.RequestException as e:
        log(f"  Erreur réseau SIREN {siren}: {e}")
        return None

    if resp.status_code == 404:
        return None
    if resp.status_code == 429:
        log("  Rate limit INPI, pause 60s...")
        time.sleep(60)
        return get_dirigeant(siren, headers)
    if resp.status_code == 401:
        return "REAUTH"  # type: ignore
    if resp.status_code != 200:
        log(f"  Erreur INPI {siren}: HTTP {resp.status_code}")
        return None

    return extract_dirigeant(resp.json())


def patch_lead(siren: str, data: Dict[str, Any]) -> bool:
    """Met à jour un lead dans Supabase."""
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
    log("Démarrage enrichissement dirigeants INPI")
    log(f"Zones : {', '.join(sorted(ZONES_DEPTS))} | NAF : {', '.join(NAFS_CIBLES)}")
    log("=" * 60)

    missing = [name for name, val in [
        ("INPI_USERNAME", INPI_USERNAME),
        ("INPI_PASSWORD", INPI_PASSWORD),
        ("SUPABASE_URL / NEXT_PUBLIC_SUPABASE_URL", SUPABASE_URL),
        ("SUPABASE_API_KEY / SUPABASE_SERVICE_ROLE_KEY", SUPABASE_API_KEY),
    ] if not val]
    if missing:
        log(f"ERREUR FATALE : secrets manquants ou vides : {', '.join(missing)}")
        log("→ Les définir dans Settings → Secrets and variables → Actions du repo GitHub.")
        sys.exit(1)

    token = inpi_login()
    headers = {"Authorization": f"Bearer {token}"}

    total_processed = 0
    total_found = 0
    api_calls = 0

    while api_calls < DAILY_QUOTA:
        remaining = DAILY_QUOTA - api_calls
        batch_size = min(BATCH_SIZE, remaining)

        leads = fetch_leads(batch_size)
        if not leads:
            log("Plus aucun lead à enrichir.")
            break

        log(f"Batch de {len(leads)} leads (API calls: {api_calls}/{DAILY_QUOTA})")

        for lead in leads:
            if api_calls >= DAILY_QUOTA:
                log(f"Quota journalier atteint ({DAILY_QUOTA})")
                break

            siren = lead["siren"]
            nom = lead.get("nom", "?")[:45]

            dirigeant = get_dirigeant(siren, headers)
            api_calls += 1

            if dirigeant == "REAUTH":
                log("Token expiré, reconnexion...")
                token = inpi_login()
                headers = {"Authorization": f"Bearer {token}"}
                dirigeant = get_dirigeant(siren, headers)
                api_calls += 1

            if dirigeant:
                total_found += 1
                role = dirigeant.pop("dirigeant_role", "")
                log(f"  [{total_processed+1}] {nom:45s} -> {dirigeant['dirigeant_prenom']} {dirigeant['dirigeant_nom']} ({role})")
                patch_lead(siren, dirigeant)
            else:
                # Marque l'échec pour ne pas re-tenter immédiatement
                patch_lead(siren, {"inpi_dirigeants_failed": datetime.now().isoformat()})

            total_processed += 1

            if total_processed % 500 == 0:
                pct = (total_found / total_processed * 100) if total_processed else 0
                log(f"── Progression: {total_processed} traités, {total_found} dirigeants ({pct:.1f}%), {api_calls} appels API ──")

            time.sleep(REQUEST_DELAY)

    log("=" * 60)
    pct = (total_found / total_processed * 100) if total_processed else 0
    log(f"TERMINÉ: {total_processed} traités, {total_found} dirigeants trouvés ({pct:.1f}%)")
    log(f"Appels API: {api_calls}/{DAILY_QUOTA}")
    log("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"ERREUR FATALE : {e}")
        sys.exit(1)
