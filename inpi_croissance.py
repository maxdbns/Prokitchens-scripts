"""
Recupere l'historique du CA via l'API INPI pour les leads finaux
et calcule la croissance annuelle.
"""

import csv
import requests
import time
from datetime import datetime

INPI_USERNAME = "maxime.debaugnies@cloudkitchens.com"
INPI_PASSWORD = "Thomas36130!"
INPI_BASE_URL = "https://registre-national-entreprises.inpi.fr/api"
INPUT_CSV = "leads_final.csv"
OUTPUT_CSV = "leads_final_croissance.csv"
LOG_FILE = "inpi_croissance.log"


def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def inpi_login():
    resp = requests.post(
        f"{INPI_BASE_URL}/sso/login",
        json={"username": INPI_USERNAME, "password": INPI_PASSWORD},
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["token"]


def parse_montant(val):
    if not val:
        return None
    try:
        return int(val.strip())
    except (ValueError, TypeError):
        return None


def extract_ca(bilan_saisi):
    bilan = bilan_saisi.get("bilanSaisi", {}).get("bilan", {})
    identite = bilan.get("identite", {})
    date_cloture = identite.get("dateClotureExercice", "")
    ca = None
    for page in bilan.get("detail", {}).get("pages", []):
        for liasse in page.get("liasses", []):
            code = liasse.get("code", "")
            if code == "FL":
                ca = parse_montant(liasse.get("m3") or liasse.get("m1"))
                break
            elif code == "FJ" and ca is None:
                ca = parse_montant(liasse.get("m3") or liasse.get("m1"))
        if ca is not None:
            break
    return date_cloture, ca


def get_historique_ca(siren, headers):
    try:
        resp = requests.get(
            f"{INPI_BASE_URL}/companies/{siren}/attachments",
            headers=headers,
            timeout=30,
        )
    except requests.RequestException as e:
        log(f"  Erreur reseau SIREN {siren}: {e}")
        return None

    if resp.status_code == 404:
        return None
    if resp.status_code == 429:
        log("  Rate limit atteint, pause 60s...")
        time.sleep(60)
        return get_historique_ca(siren, headers)
    if resp.status_code == 401:
        return "REAUTH"
    if resp.status_code != 200:
        log(f"  HTTP {resp.status_code} SIREN {siren}: {resp.text[:200]}")
        return None

    bilans = resp.json().get("bilansSaisis", [])
    historique = []
    for bs in bilans:
        if bs.get("confidentiality") == "Public" and not bs.get("deleted", False):
            date_cloture, ca = extract_ca(bs)
            if ca is not None:
                historique.append((date_cloture, ca))
    # Trie par date decroissante
    historique.sort(key=lambda x: x[0], reverse=True)
    return historique


def calculer_croissance(historique):
    """Retourne (ca_recent, ca_precedent, pct_croissance) si au moins 2 annees."""
    if len(historique) < 2:
        return None, None, None
    ca_recent = historique[0][1]
    ca_precedent = historique[1][1]
    if ca_precedent == 0:
        return ca_recent, ca_precedent, None
    pct = (ca_recent - ca_precedent) / ca_precedent * 100
    return ca_recent, ca_precedent, pct


def main():
    log("=" * 60)
    log("Recuperation historique CA INPI")
    log("=" * 60)

    with open(INPUT_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        leads = list(reader)
        fieldnames = reader.fieldnames

    extra_cols = ["ca_recent", "ca_precedent", "ca_croissance_pct", "inpi_historique"]
    for col in extra_cols:
        if col not in fieldnames:
            fieldnames.append(col)

    token = inpi_login()
    headers = {"Authorization": f"Bearer {token}"}

    total = len(leads)
    avec_ca = 0

    for i, lead in enumerate(leads, 1):
        siren = lead.get("SIREN", "")
        nom = lead.get("Nom", "?")
        log(f"[{i}/{total}] {nom[:40]} ({siren})")

        historique = get_historique_ca(siren, headers)
        if historique == "REAUTH":
            log("  Token expiré, reconnexion...")
            token = inpi_login()
            headers = {"Authorization": f"Bearer {token}"}
            historique = get_historique_ca(siren, headers)

        if historique and len(historique) >= 2:
            ca_recent, ca_precedent, pct = calculer_croissance(historique)
            lead["ca_recent"] = ca_recent
            lead["ca_precedent"] = ca_precedent
            lead["ca_croissance_pct"] = f"{pct:.1f}" if pct is not None else ""
            lead["inpi_historique"] = "; ".join(f"{d}:{ca:,}" for d, ca in historique)
            avec_ca += 1
            log(f"  CA recent={ca_recent:,} | precedent={ca_precedent:,} | croissance={pct:.1f}%")
        else:
            lead["ca_recent"] = ""
            lead["ca_precedent"] = ""
            lead["ca_croissance_pct"] = ""
            lead["inpi_historique"] = ""
            log(f"  Pas assez d'historique CA")

        time.sleep(0.4)

    with open(OUTPUT_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(leads)

    log("=" * 60)
    log(f"TERMINE: {total} leads, {avec_ca} avec historique CA")
    log(f"Sortie: {OUTPUT_CSV}")
    log("=" * 60)


if __name__ == "__main__":
    main()
