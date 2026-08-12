"""
Génération d'emails par pattern (prenom.nom@domaine) + validation MX.

Pour les leads avec dirigeant + site_web mais sans email :
1. Extrait le domaine du site web
2. Vérifie que le domaine a un enregistrement MX (accepte du courrier)
3. Génère les patterns les plus courants en France
4. Écrit le meilleur email candidat dans Supabase

Ne remplace pas l'email existant — ne traite que email IS NULL.
"""

import os
import sys
import re
import time
import socket
import requests
from datetime import datetime
from urllib.parse import urlparse
from typing import Optional, List, Dict, Any

import prokitchens_env
prokitchens_env.load_env()

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_API_KEY = os.environ["SUPABASE_API_KEY"]
SUPABASE_TABLE = os.environ.get("SUPABASE_TABLE", "leads")

MAX_LEADS = int(os.environ.get("EMAIL_PATTERN_BATCH", "1000"))
os.makedirs("logs", exist_ok=True)
LOG_FILE = os.path.join("logs", "enrich_email_patterns.log")

# Cache MX pour éviter de re-vérifier le même domaine
_mx_cache: Dict[str, bool] = {}

# Domaines gratuits/génériques à exclure du pattern matching
FREE_DOMAINS = {
    "gmail.com", "hotmail.fr", "hotmail.com", "outlook.fr", "outlook.com",
    "yahoo.fr", "yahoo.com", "free.fr", "orange.fr", "wanadoo.fr",
    "sfr.fr", "laposte.net", "bbox.fr", "numericable.fr", "live.fr",
    "msn.com", "aol.com", "icloud.com", "protonmail.com", "gmx.fr",
}


def log(msg: str):
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


def extract_domain(url: str) -> Optional[str]:
    """Extrait le domaine propre depuis une URL."""
    if not url:
        return None
    url = url.strip()
    if not url.startswith("http"):
        url = "https://" + url
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path
        domain = domain.lower().strip()
        if domain.startswith("www."):
            domain = domain[4:]
        if "." not in domain:
            return None
        return domain
    except Exception:
        return None


def check_mx(domain: str) -> bool:
    """Vérifie qu'un domaine a un enregistrement MX (accepte du courrier)."""
    if domain in _mx_cache:
        return _mx_cache[domain]
    try:
        import dns.resolver
        answers = dns.resolver.resolve(domain, "MX")
        result = len(answers) > 0
    except ImportError:
        # dnspython pas installé — fallback socket
        result = _check_mx_socket(domain)
    except Exception:
        result = False
    _mx_cache[domain] = result
    return result


def _check_mx_socket(domain: str) -> bool:
    """Fallback MX check via socket (moins fiable mais sans dépendance)."""
    try:
        socket.getaddrinfo(domain, 25, socket.AF_INET, socket.SOCK_STREAM)
        return True
    except Exception:
        pass
    try:
        socket.getaddrinfo("mail." + domain, 25, socket.AF_INET, socket.SOCK_STREAM)
        return True
    except Exception:
        return False


def normalize_name(name: str) -> str:
    """Normalise un nom/prénom pour un email : minuscules, sans accents ni espaces."""
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", name.strip().lower())
    ascii_name = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"[^a-z\-]", "", ascii_name)


def generate_email_patterns(prenom: str, nom: str, domain: str) -> List[str]:
    """Génère les patterns email les plus courants en France."""
    p = normalize_name(prenom)
    n = normalize_name(nom)
    if not p or not n or not domain:
        return []

    return [
        f"{p}.{n}@{domain}",       # prenom.nom (le plus courant en France)
        f"{p}{n[0]}@{domain}",      # prenomn
        f"{p[0]}{n}@{domain}",      # pnom
        f"{p[0]}.{n}@{domain}",     # p.nom
        f"{p}@{domain}",            # prenom
        f"{n}@{domain}",            # nom
        f"{p}-{n}@{domain}",        # prenom-nom
        f"contact@{domain}",        # fallback générique
        f"info@{domain}",           # fallback générique
    ]


def fetch_leads(limit: int) -> List[Dict[str, Any]]:
    """Leads avec dirigeant + site_web, sans email."""
    params = {
        "select": "siren,nom,dirigeant_nom,dirigeant_prenom,site_web,email",
        "site_web": "not.is.null",
        "email": "is.null",
        "dirigeant_nom": "not.is.null",
        "dirigeant_prenom": "not.is.null",
        "statut": "neq.ferme",
        "limit": limit,
        "order": "score_total.desc.nullslast",
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
        log(f"Erreur fetch leads: {e}")
        return []


def patch_lead(siren: str, data: Dict[str, Any]) -> bool:
    try:
        resp = requests.patch(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}?siren=eq.{siren}",
            headers=supabase_write_headers(),
            json=data,
            timeout=15,
        )
        return resp.status_code in (200, 204)
    except Exception:
        return False


def main():
    log("=" * 60)
    log(f"Email pattern generation — batch {MAX_LEADS}")
    log("=" * 60)

    leads = fetch_leads(MAX_LEADS)
    log(f"{len(leads)} leads avec dirigeant + site web, sans email")

    if not leads:
        log("Rien à faire.")
        return

    generated = 0
    mx_ok = 0
    mx_fail = 0
    skipped_free = 0

    for i, lead in enumerate(leads, 1):
        siren = lead["siren"]
        prenom = lead.get("dirigeant_prenom", "")
        nom = lead.get("dirigeant_nom", "")
        site_web = lead.get("site_web", "")

        domain = extract_domain(site_web)
        if not domain or domain in FREE_DOMAINS:
            skipped_free += 1
            continue

        if not check_mx(domain):
            mx_fail += 1
            continue

        mx_ok += 1
        patterns = generate_email_patterns(prenom, nom, domain)
        if not patterns:
            continue

        best = patterns[0]
        secondaires = ", ".join(patterns[1:5]) if len(patterns) > 1 else ""

        update = {"email": best}
        if secondaires:
            update["emails_secondaires"] = secondaires

        if patch_lead(siren, update):
            generated += 1
            if generated <= 20 or generated % 100 == 0:
                log(f"  [{i}] {prenom} {nom} → {best}")

        if i % 100 == 0:
            log(f"── {i}/{len(leads)} | {generated} générés | MX ok={mx_ok} fail={mx_fail} ──")

    log("=" * 60)
    log(f"TERMINÉ: {generated}/{len(leads)} emails générés")
    log(f"  MX valides: {mx_ok}, MX invalides: {mx_fail}, domaines gratuits: {skipped_free}")
    log("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"ERREUR FATALE: {e}")
        sys.exit(1)
