"""
Genere une liste de prospects ayant ouvert un point de vente dans l'annee,
dans les zones cibles (IDF, Marseille, Lille, Lyon), et verifie s'ils sont
dans Salesforce / BOB.
"""

import csv
import os
import re
import sys
from pathlib import Path

import pandas as pd
import requests
from rapidfuzz import fuzz, process

sys.path.insert(0, "/zpool/one/maxime.debaugnies")
import prokitchens_env
prokitchens_env.load_env()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY")

ACCOUNTS_FILE = "All accounts - France - incl. contacts-2026-07-23-14-47-11.xlsx"
BOB_FILE = "BOB.xlsx"
OUTPUT_CSV = "prospects_ouvertures_recentes_zones.csv"

TARGET_ZONES = {"Île-de-France", "Marseille", "Lyon", "Lille"}
FUZZY_THRESHOLD = 85

MOTS_VIDES = {
    "LE", "LA", "LES", "DU", "DE", "DES", "ET", "EN", "A", "AU", "AUX", "FR", "FRANCE",
    "SAS", "SARL", "SASU", "EURL", "SCOP", "SCIC", "SA", "SEMS", "SEM", "SNC", "SCA",
}


def normaliser_nom(name: str) -> str:
    if not name:
        return ""
    name = str(name).upper()
    # Retire les prefixes entre crochets comme [PAR], [UK], [MARSEILLE], etc.
    name = re.sub(r"^\s*\[.*?\]\s*-?\s*", "", name)
    name = re.sub(r"\[.*?\]", "", name)
    name = re.sub(r"\(OLD\)", "", name, flags=re.I)
    name = re.sub(r"\bOLD\b", "", name, flags=re.I)
    name = re.sub(r"\bFR\s*-\s*PAR\s*-?", "", name, flags=re.I)
    name = re.sub(r"\b(SAS|SASU|SARL|EURL|SCOP|SCIC|SA|SEMS|SEM|SNC|SCA)\b", "", name, flags=re.I)
    name = re.sub(r"[^A-Z0-9&\s]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def supabase_headers():
    return {
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}",
        "Content-Type": "application/json",
    }


def charger_comptes_salesforce(path: str) -> list[str]:
    df = pd.read_excel(path, header=9)
    df = df[df["Account Name"].notna()].copy()
    df = df.drop_duplicates(subset=["Account Name"], keep="first")
    return [row["Account Name"] for _, row in df.iterrows()]


def charger_bob(path: str) -> list[str]:
    df = pd.read_excel(path, header=11)
    df = df[df["Account Name"].notna()].copy()
    df = df[~df["Account Status  ↑"].isin({"Subtotal", "Total"})]
    return sorted({normaliser_nom(n) for n in df["Account Name"] if n and len(str(n)) > 2})


def charger_leads_ouvertures_recentes() -> list[dict]:
    """Recupere tous les leads avec ouvertures recentes dans les zones cibles."""
    url = f"{SUPABASE_URL}/rest/v1/leads"
    params = {
        "select": "nom,nom_legal,aliases,siren,code_naf,score,score_ca,score_sites,score_croissance,nb_etablissements,sites_ouverts_12m,derniere_ouverture,zone,chiffre_affaires,telephone,email,site_web,segment,statut",
        "sites_ouverts_12m": "gt.0",
        "zone": "in.(%s)" % ",".join(TARGET_ZONES),
        "order": "sites_ouverts_12m.desc,score.desc",
    }

    all_leads = []
    offset = 0
    page_size = 1000
    while True:
        headers = {**supabase_headers(), "Range": f"{offset}-{offset + page_size - 1}"}
        resp = requests.get(url, params=params, headers=headers)
        if resp.status_code == 416:
            break
        resp.raise_for_status()
        data = resp.json()
        if not data:
            break
        all_leads.extend(data)
        offset += page_size
        if len(data) < page_size:
            break
    return all_leads


def est_dans_bob(nom: str, book_noms: list[str]) -> tuple[bool, str | None]:
    n = normaliser_nom(nom)
    if not n or len(n) < 3:
        return False, None
    if n in book_noms:
        return True, n
    if len(n) < 8:
        return False, None
    match = process.extractOne(n, book_noms, scorer=fuzz.token_set_ratio)
    if match and match[1] >= FUZZY_THRESHOLD:
        if est_nom_generique(match[0]):
            return False, None
        return True, f"{match[0]} ({match[1]:.0f})"
    return False, None


def est_nom_generique(nom: str) -> bool:
    mots = {"SUSHI", "PIZZA", "RESTAURANT", "CAFE", "BOULANGERIE", "PATISSERIE", "SASU", "SARL", "SAS", "STREET FOOD", "SANDWICH", "BURGER", "KEBAB", "TACOS"}
    n = normaliser_nom(nom)
    return n in mots or len(n) < 5


def trouver_dans_salesforce(nom: str, sf_noms: list[str]) -> tuple[str | None, float]:
    match = process.extractOne(nom, sf_noms, scorer=fuzz.token_set_ratio)
    if match and match[1] >= FUZZY_THRESHOLD:
        if est_nom_generique(match[0]):
            return None, 0.0
        return match[0], match[1]
    return None, 0.0


def est_nom_app_interessant(nom: str) -> bool:
    """Exclut les noms qui semblent etre des codes internes ou placeholders."""
    if not nom:
        return False
    n = normaliser_nom(nom)
    if len(n) < 3:
        return False
    if n.startswith("REF ") or n.startswith("CODE INTERNE") or n.startswith("KDSUSHI"):
        return False
    if n.startswith("CODE ") and len(n) < 20:
        return False
    return True


def main():
    base = Path(__file__).parent
    accounts_path = base / ACCOUNTS_FILE
    bob_path = base / BOB_FILE
    output_path = base / OUTPUT_CSV

    print("Chargement des comptes Salesforce...")
    sf_noms = charger_comptes_salesforce(accounts_path)
    sf_norm = {normaliser_nom(n): n for n in sf_noms}
    print(f"  {len(sf_noms)} comptes")

    print("Chargement du BOB...")
    book_noms = charger_bob(bob_path)
    print(f"  {len(book_noms)} noms uniques")

    print("Recuperation des leads avec ouvertures recentes dans les zones cibles...")
    leads = charger_leads_ouvertures_recentes()
    print(f"  {len(leads)} leads charges")

    resultats = []
    for lead in leads:
        nom_app = lead.get("nom") or lead.get("nom_legal") or ""
        if not est_nom_app_interessant(nom_app):
            continue

        in_bob, match_bob = est_dans_bob(nom_app, book_noms)
        if in_bob:
            continue

        sf_match, sf_score = trouver_dans_salesforce(nom_app, sf_noms)
        in_salesforce = sf_match is not None

        if not in_salesforce and lead.get("aliases"):
            for alias in [a.strip() for a in str(lead["aliases"]).split(",") if a.strip()]:
                sf_match, sf_score = trouver_dans_salesforce(alias, sf_noms)
                if sf_match:
                    in_salesforce = True
                    break

        if not in_salesforce:
            n_norm = normaliser_nom(nom_app)
            if n_norm and n_norm in sf_norm:
                in_salesforce = True
                sf_match = sf_norm[n_norm]
                sf_score = 100.0

        resultats.append({
            "Nom App": nom_app,
            "SIREN": lead.get("siren"),
            "Code NAF": lead.get("code_naf"),
            "Score App": lead.get("score"),
            "Score CA": lead.get("score_ca"),
            "Score Sites": lead.get("score_sites"),
            "Score Croissance": lead.get("score_croissance"),
            "CA": lead.get("chiffre_affaires"),
            "Nb Etablissements": lead.get("nb_etablissements"),
            "Sites ouverts 12m": lead.get("sites_ouverts_12m"),
            "Derniere ouverture": lead.get("derniere_ouverture"),
            "Zone": lead.get("zone"),
            "Segment": lead.get("segment"),
            "Telephone": lead.get("telephone"),
            "Email": lead.get("email"),
            "Site Web": lead.get("site_web"),
            "Dans Salesforce": "Oui" if in_salesforce else "Non",
            "Nom Salesforce": sf_match if in_salesforce else "",
            "Matching Salesforce": round(sf_score, 1) if in_salesforce else "",
            "Statut": lead.get("statut"),
        })

    print(f"\nProspects avec ouvertures recentes hors BOB : {len(resultats)}")
    print(f"  Dont deja dans Salesforce : {sum(1 for r in resultats if r['Dans Salesforce'] == 'Oui')}")
    print(f"  Dont a creer dans Salesforce : {sum(1 for r in resultats if r['Dans Salesforce'] == 'Non')}")

    if not resultats:
        print("Aucun resultat.")
        return

    resultats.sort(key=lambda x: (x["Sites ouverts 12m"] or 0, x["Score App"] or 0), reverse=True)

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=resultats[0].keys())
        writer.writeheader()
        writer.writerows(resultats)

    print(f"Fichier genere : {output_path}")


if __name__ == "__main__":
    main()
