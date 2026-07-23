"""
Enrichissement des contacts (email + téléphone) à partir du site web.

Pour chaque lead ayant un site web mais pas d'email, le script :
1. Télécharge la page d'accueil
2. Cherche un pattern email dans le HTML
3. Cherche éventuellement dans les pages /contact et /mentions-legales
4. Met à jour Supabase avec les emails trouvés

Limité par défaut à MAX_LEADS pour rester dans les quotas et le temps d'exécution.
"""

import os
import sys
import re
import requests
import time
from urllib.parse import urljoin, urlparse
from datetime import datetime
from typing import List, Dict, Any, Optional, Set

import prokitchens_env
prokitchens_env.load_env()

# ─── Config ───
SUPABASE_URL = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_TABLE = os.environ.get("SUPABASE_TABLE", "leads")

MAX_LEADS = 200
BATCH_SIZE = 50
REQUEST_TIMEOUT = 10
REQUEST_DELAY = 0.5
LOG_FILE = "/zpool/one/maxime.debaugnies/enrich_contact.log"

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", re.IGNORECASE)
PHONE_REGEX = re.compile(r"[\+]?[0-9\s\.\-\(\)]{8,}")

# Exclusions d'emails génériques à ne pas garder
EXCLUDED_EMAILS = {
    "example.com", "domain.com", "test.com", "email.com", "nom@domaine.com",
    "contact@example.com", "votre@email.com", "vous@exemple.com", "mail@domain.com",
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


def normalize_url(url: str) -> str:
    """Ajoute https:// si nécessaire et nettoie l'URL."""
    url = url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    return url


def extract_emails(text: str) -> Set[str]:
    """Extrait les emails uniques d'un texte HTML."""
    found = set()
    for match in EMAIL_REGEX.findall(text):
        email = match.lower().strip()
        domain = email.split("@")[-1]
        if domain in EXCLUDED_EMAILS:
            continue
        if "example" in domain or "domain" in domain:
            continue
        found.add(email)
    return found


def extract_phones(text: str) -> Set[str]:
    """Extrait les téléphones potentiels d'un texte."""
    found = set()
    for match in PHONE_REGEX.findall(text):
        digits = re.sub(r"\D", "", match)
        if len(digits) >= 10:
            found.add(match.strip())
    return found


def fetch_page(url: str) -> Optional[str]:
    """Télécharge une page web et retourne le HTML."""
    try:
        resp = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 ProKitchens LeadBot"},
            allow_redirects=True,
        )
        if resp.status_code != 200:
            return None
        return resp.text
    except Exception:
        return None


def find_linked_pages(html: str, base_url: str) -> List[str]:
    """Trouve les liens vers contact et mentions légales."""
    candidates = []
    patterns = ["contact", "mentions-legales", "mentions_legales", "legal", "a-propos", "about"]
    for pattern in patterns:
        if pattern in html.lower():
            # Recherche simple du href contenant le pattern
            href_match = re.search(rf'href=["\']([^"\']*{pattern}[^"\']*)["\']', html, re.IGNORECASE)
            if href_match:
                href = href_match.group(1)
                candidates.append(urljoin(base_url, href))
    return candidates[:3]


def enrich_from_website(site_web: str) -> Dict[str, Any]:
    """
    Tente d'extraire email et téléphone depuis le site web.
    Retourne un dict avec email, telephone, et emails_secondaires.
    """
    url = normalize_url(site_web)
    html = fetch_page(url)
    if not html:
        return {}

    all_emails = extract_emails(html)
    all_phones = extract_phones(html)

    # Pages liées
    linked = find_linked_pages(html, url)
    for linked_url in linked:
        time.sleep(0.3)
        linked_html = fetch_page(linked_url)
        if linked_html:
            all_emails.update(extract_emails(linked_html))
            all_phones.update(extract_phones(linked_html))

    if not all_emails and not all_phones:
        return {}

    result: Dict[str, Any] = {}

    if all_emails:
        # Choisir le meilleur email : préférence contact@, info@, hello@, sinon le premier
        preferred = None
        for prefix in ["contact", "info", "hello", "bonjour", "accueil", "direction"]:
            for email in all_emails:
                if email.startswith(prefix + "@"):
                    preferred = email
                    break
            if preferred:
                break
        if not preferred:
            preferred = sorted(all_emails)[0]

        result["email"] = preferred
        remaining = all_emails - {preferred}
        if remaining:
            result["emails_secondaires"] = ", ".join(sorted(remaining))

    if all_phones:
        # Garder le téléphone le plus long (probablement le plus complet)
        best_phone = sorted(all_phones, key=lambda x: len(re.sub(r"\D", "", x)), reverse=True)[0]
        result["telephone"] = best_phone

    return result


def fetch_leads_to_enrich(limit: int) -> List[Dict[str, Any]]:
    """Récupère les leads avec site web mais sans email, triés par score."""
    params = {
        "select": "id,siren,nom,site_web,telephone",
        "site_web": "not.is.null",
        "email": "is.null",
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
        log(f"Erreur récupération leads : {e}")
        return []


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
    log("Enrichissement des contacts (email + téléphone)")
    log(f"Max leads : {MAX_LEADS}")
    log("=" * 60)

    leads = fetch_leads_to_enrich(MAX_LEADS)
    log(f"{len(leads)} leads à enrichir")

    if not leads:
        log("Aucun lead à enrichir. Fin.")
        return

    enriched_count = 0
    email_count = 0
    phone_count = 0

    for i, lead in enumerate(leads, 1):
        siren = lead.get("siren", "")
        nom = lead.get("nom", "?")[:40]
        site_web = lead.get("site_web", "")

        if not site_web:
            continue

        log(f"[{i}/{len(leads)}] {nom} -> {site_web[:50]}")

        try:
            result = enrich_from_website(site_web)
        except Exception as e:
            log(f"  Erreur enrichissement {siren}: {e}")
            continue

        if result:
            enriched_count += 1
            if "email" in result:
                email_count += 1
            if "telephone" in result:
                phone_count += 1
            log(f"  ✓ {result.get('email', '')} | {result.get('telephone', '')}")
            patch_lead(siren, result)

        time.sleep(REQUEST_DELAY)

    log("=" * 60)
    log(f"TERMINÉ : {enriched_count}/{len(leads)} leads enrichis")
    log(f"  Emails trouvés : {email_count}")
    log(f"  Téléphones trouvés : {phone_count}")
    log("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"ERREUR FATALE : {e}")
        sys.exit(1)
