"""
Hot leads report — génère un rapport des opportunités qualitatives du jour.

Critères de sélection :
- score_total >= 40
- Au moins un signal fort :
  * nouvelle ouverture récente (6 mois)
  * croissance CA > 15%
  * appel d'offres public (marché attribué ou avis)
  * dirigeant récemment enrichi

Sortie : hot_leads_YYYY-MM-DD.csv trié par score décroissant.
"""

import os
import sys
import csv
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

# ─── Config ───
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://hxjryfaakdpwfgseirik.supabase.co")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY", "sb_publishable_a7xpn8srwByQrW1rXwpdlw_eQnwAoHT")
SUPABASE_TABLE = os.environ.get("SUPABASE_TABLE", "leads")

SCORE_THRESHOLD = 40
OUTPUT_CSV = f"hot_leads_{datetime.now().strftime('%Y-%m-%d')}.csv"
LOG_FILE = "/zpool/one/maxime.debaugnies/hot_leads.log"


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


def fetch_hot_leads() -> List[Dict[str, Any]]:
    """Récupère les leads avec score_total >= seuil et au moins un contact."""
    six_months_ago = (datetime.now() - timedelta(days=180)).isoformat()

    params = {
        "select": "id,siren,nom,ville,code_postal,zone,code_naf,telephone,site_web,email,score_total,chiffre_affaires,nb_etablissements,croissance_ca,sites_ouverts_12m,derniere_ouverture,nb_tenders,nb_tender_notices,dirigeant_prenom,dirigeant_nom,created_at",
        "score_total": f"gte.{SCORE_THRESHOLD}",
        "statut": "neq.ferme",
        "or": "telephone.not.is.null,site_web.not.is.null,email.not.is.null",
        "limit": 1000,
        "order": "score_total.desc",
    }

    try:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}",
            params=params,
            headers=supabase_headers(),
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log(f"Erreur récupération leads : {e}")
        return []


def detect_signals(lead: Dict[str, Any]) -> List[str]:
    """Détecte les signaux d'intention d'achat pour un lead."""
    signals = []

    # Nouvelle ouverture récente
    derniere_ouverture = lead.get("derniere_ouverture")
    sites_ouverts_12m = lead.get("sites_ouverts_12m") or 0
    if derniere_ouverture:
        try:
            date_ouverture = datetime.fromisoformat(str(derniere_ouverture).replace("Z", "+00:00"))
            if date_ouverture >= datetime.now() - timedelta(days=180):
                signals.append(f"nouvelle_ouverture_6m ({sites_ouverts_12m} sites/12m)")
        except Exception:
            pass

    # Croissance CA
    croissance = lead.get("croissance_ca")
    if croissance is not None:
        if croissance >= 30:
            signals.append(f"croissance_forte_{croissance}%")
        elif croissance >= 15:
            signals.append(f"croissance_{croissance}%")

    # Appels d'offres
    tenders = lead.get("nb_tenders") or 0
    notices = lead.get("nb_tender_notices") or 0
    if tenders > 0:
        signals.append(f"tenders_attribues_{tenders}")
    if notices > 0:
        signals.append(f"appels_offres_{notices}")

    # Dirigeant enrichi
    if lead.get("dirigeant_nom"):
        signals.append("dirigeant_identifie")

    # Contact complet
    if lead.get("telephone") and lead.get("site_web") and lead.get("email"):
        signals.append("contact_complet")
    elif lead.get("telephone") and lead.get("site_web"):
        signals.append("telephone_et_site")

    # Multi-sites
    nb_sites = lead.get("nb_etablissements") or 0
    if nb_sites >= 10:
        signals.append("chaine_10+_sites")
    elif nb_sites >= 5:
        signals.append("chaine_5+_sites")
    elif nb_sites >= 3:
        signals.append("multi_sites")

    return signals


def format_amount(amount: Optional[Any]) -> str:
    if amount is None:
        return ""
    try:
        val = float(amount)
        if val >= 1_000_000:
            return f"{val/1_000_000:.1f}M€"
        if val >= 1_000:
            return f"{val/1_000:.0f}K€"
        return f"{val:.0f}€"
    except (ValueError, TypeError):
        return str(amount)


def enrich_lead(lead: Dict[str, Any]) -> Dict[str, Any]:
    """Ajoute les signaux et formatte les champs pour le rapport."""
    signals = detect_signals(lead)
    signal_score = min(len(signals) * 5, 25)  # bonus de 5 points par signal, max 25

    return {
        "siren": lead.get("siren", ""),
        "nom": lead.get("nom", ""),
        "ville": lead.get("ville", ""),
        "code_postal": lead.get("code_postal", ""),
        "zone": lead.get("zone", ""),
        "code_naf": lead.get("code_naf", ""),
        "score_total": lead.get("score_total", 0) or 0,
        "signal_score": signal_score,
        "score_final": (lead.get("score_total", 0) or 0) + signal_score,
        "nb_signaux": len(signals),
        "signaux": " | ".join(signals),
        "telephone": lead.get("telephone", ""),
        "site_web": lead.get("site_web", ""),
        "email": lead.get("email", ""),
        "dirigeant": " ".join(filter(None, [lead.get("dirigeant_prenom", ""), lead.get("dirigeant_nom", "")])).strip(),
        "ca": format_amount(lead.get("chiffre_affaires")),
        "nb_sites": lead.get("nb_etablissements", 0) or 0,
        "croissance_ca": lead.get("croissance_ca", ""),
        "tenders": lead.get("nb_tenders", 0) or 0,
        "appels_offres": lead.get("nb_tender_notices", 0) or 0,
        "derniere_ouverture": lead.get("derniere_ouverture", ""),
        "date_creation_lead": lead.get("created_at", ""),
    }


def write_csv(leads: List[Dict[str, Any]]):
    if not leads:
        log("Aucun hot lead à exporter.")
        return

    fieldnames = [
        "score_final", "score_total", "signal_score", "nb_signaux", "signaux",
        "siren", "nom", "ville", "code_postal", "zone", "code_naf",
        "telephone", "site_web", "email", "dirigeant",
        "ca", "nb_sites", "croissance_ca", "tenders", "appels_offres",
        "derniere_ouverture", "date_creation_lead",
    ]

    with open(OUTPUT_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(leads)

    log(f"{len(leads)} hot leads exportés vers {OUTPUT_CSV}")


def main():
    log("=" * 60)
    log("Hot Leads Report")
    log(f"Seuil score_total : {SCORE_THRESHOLD}")
    log("=" * 60)

    raw_leads = fetch_hot_leads()
    log(f"{len(raw_leads)} leads récupérés depuis Supabase")

    enriched = [enrich_lead(lead) for lead in raw_leads]

    # Ne garder que ceux qui ont au moins un signal
    hot = [lead for lead in enriched if lead["nb_signaux"] > 0]
    hot.sort(key=lambda x: x["score_final"], reverse=True)

    log(f"{len(hot)} leads avec au moins un signal qualitatif")

    write_csv(hot)

    # Top 10 affiché en console
    log("\nTop 10 hot leads :")
    for lead in hot[:10]:
        log(
            f"  Score {lead['score_final']:>3} | {lead['nom'][:40]:<40} | "
            f"{lead['ville'][:20]:<20} | {lead['signaux'][:60]}"
        )

    log("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"ERREUR FATALE : {e}")
        sys.exit(1)
