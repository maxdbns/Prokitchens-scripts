"""
Genere une liste de prospects qualifies depuis l'app Prokitchens (Supabase),
verifie si chacun est deja dans Salesforce ou dans le BOB,
et produit un fichier de comptes a ajouter au BOB.
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
OUTPUT_CSV = "prospects_qualifieds_app_hors_bob.csv"

SCORE_MIN = 40
FUZZY_THRESHOLD = 80

MOTS_VIDES = {
    "LE", "LA", "LES", "DU", "DE", "DES", "ET", "EN", "A", "AU", "AUX", "FR", "FRANCE",
    "SAS", "SARL", "SASU", "EURL", "SCOP", "SCIC", "SA", "SEMS", "SEM", "SNC", "SCA",
}


def normaliser_nom(name: str) -> str:
    if not name:
        return ""
    name = str(name).upper()
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


def charger_leads_supabase() -> list[dict]:
    url = f"{SUPABASE_URL}/rest/v1/leads"
    params = {
        "select": "nom,nom_legal,aliases,siren,code_naf,score,score_ca,score_sites,score_croissance,nb_etablissements,sites_ouverts_12m,derniere_ouverture,zone,chiffre_affaires,telephone,email,site_web,segment,statut",
        "score": f"gte.{SCORE_MIN}",
        "order": "score.desc",
        "limit": 1000,
    }
    headers = {**supabase_headers(), "Range": "0-999"}
    resp = requests.get(url, params=params, headers=headers)
    resp.raise_for_status()
    return resp.json()


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
        return True, f"{match[0]} ({match[1]:.0f})"
    return False, None


def trouver_dans_salesforce(nom: str, sf_noms: list[str]) -> tuple[str | None, float]:
    match = process.extractOne(nom, sf_noms, scorer=fuzz.token_set_ratio)
    if match and match[1] >= FUZZY_THRESHOLD:
        return match[0], match[1]
    return None, 0.0


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

    print(f"Recuperation des leads App avec score >= {SCORE_MIN}...")
    leads = charger_leads_supabase()
    print(f"  {len(leads)} leads charges")

    resultats = []
    for lead in leads:
        nom_app = lead.get("nom") or lead.get("nom_legal") or ""
        if not nom_app:
            continue

        # Skip if in BOB
        in_bob, match_bob = est_dans_bob(nom_app, book_noms)
        if in_bob:
            continue

        # Check if in Salesforce
        sf_match, sf_score = trouver_dans_salesforce(nom_app, sf_noms)
        in_salesforce = sf_match is not None

        # If not in Salesforce, also check aliases
        if not in_salesforce and lead.get("aliases"):
            for alias in [a.strip() for a in str(lead["aliases"]).split(",") if a.strip()]:
                sf_match, sf_score = trouver_dans_salesforce(alias, sf_noms)
                if sf_match:
                    in_salesforce = True
                    break

        # Check if nom normalised is in Salesforce normalised
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

    print(f"\nProspects qualifies App hors BOB : {len(resultats)}")
    print(f"  Dont deja dans Salesforce : {sum(1 for r in resultats if r['Dans Salesforce'] == 'Oui')}")
    print(f"  Dont a creer dans Salesforce : {sum(1 for r in resultats if r['Dans Salesforce'] == 'Non')}")

    if not resultats:
        print("Aucun resultat.")
        return

    resultats.sort(key=lambda x: x["Score App"] or 0, reverse=True)

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=resultats[0].keys())
        writer.writeheader()
        writer.writerows(resultats)

    print(f"Fichier genere : {output_path}")


if __name__ == "__main__":
    main()
