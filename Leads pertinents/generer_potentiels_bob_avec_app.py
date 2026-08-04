"""
Genere une liste de comptes Salesforce a potentiellement ajouter au BOB,
en utilisant les donnees du site Prokitchens (Supabase) : leads avec score eleve
et ouvertures recentes de points de vente.
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

# Configuration
ACCOUNTS_FILE = "All accounts - France - incl. contacts-2026-07-23-14-47-11.xlsx"
BOB_FILE = "BOB.xlsx"
OUTPUT_CSV = "potentiels_bob_ouverts_recents.csv"

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY")

# Criteres Supabase
SCORE_MIN = 50
SITES_OUVERTS_MIN = 1

FUZZY_THRESHOLD = 85

MOTS_VIDES = {
    "LE", "LA", "LES", "DU", "DE", "DES", "ET", "EN", "A", "AU", "AUX", "FR", "FRANCE",
    "SAS", "SARL", "SASU", "EURL", "SCOP", "SCIC", "SA", "SEMS", "SEM", "SNC", "SCA",
}
MOTS_GENERIQUES = {
    "SUSHI", "BURGER", "TACOS", "CHICKEN", "POULET", "PIZZA", "PASTA", "WOK", "BOWL",
    "DIM", "SUM", "RAMEN", "NOODLE", "BURRITOS", "BAGEL", "FRESH", "TIME", "FACTORY",
    "WINGS", "ROOSTERS", "BAO", "PITA", "KEBAB", "CROUSTY", "SNACK", "CAFE", "COFFEE",
    "RESTO", "RESTAURANT", "GRILL", "FAST", "FOOD", "GO", "GOOD", "MISTER", "MASTER",
    "ORIGINAL", "TASTY", "NEW", "KING", "AVENUE", "DELI", "DAILY", "MARKET", "SHOP",
    "BAR", "HOUSE", "LAB", "POKE", "BISTROT", "COMPTOIR", "BISTRO", "TABLE", "DELICES",
    "KITCHEN", "LUNCH", "BRUNCH", "DINER", "BUFFET", "PATISSERIE", "BOULANGERIE",
    "BOULANGE", "SANDWICH", "SALON", "THE", "CHOCOLAT", "GOURMAND", "GOURMET",
    "CROISSANTERIE", "PAIN", "VIENNOISERIE", "BREAD", "WAY", "GOODIES", "BUN", "MIAN",
    "FAN", "NANA", "MAMA", "PAPA", "MAMIE", "MAMAN", "PAPI", "BABY", "MISS", "QUEEN",
    "STREET", "CORNER", "PLACE", "EAT", "EATS", "FAMILY", "FRIENDS", "HOUSE", "CITY",
    "PARIS", "LYON", "MARSEILLE", "BORDEAUX", "LILLE", "NANTES", "STRASBOURG",
    "TOULOUSE", "NICE", "MONTPELLIER", "RENNES", "TOURS", "FRANCHIS", "FRANCHISE",
    "GROUPE", "HOLDING", "RESTAURANTS", "SYSTEM", "TRUCK", "BAR", "DELI", "CAFE",
    "RESTO", "FOOD", "BISTRO", "KITCHEN",
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


def tokens_significatifs(name: str) -> list[str]:
    return [t for t in normaliser_nom(name).split() if t and t not in MOTS_VIDES and len(t) > 2]


def tokens_distinctifs(name: str) -> list[str]:
    return [t for t in tokens_significatifs(name) if t not in MOTS_GENERIQUES]


def supabase_headers():
    return {
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}",
        "Content-Type": "application/json",
    }


def charger_comptes_salesforce(path: str) -> dict:
    """Charge les comptes Salesforce et retourne un dict nom -> row."""
    df = pd.read_excel(path, header=9)
    df = df[df["Account Name"].notna()].copy()
    df["_contact_ok"] = df.apply(lambda r: bool(str(r.get("Phone", "")).strip() or str(r.get("Mobile", "")).strip() or str(r.get("Email", "")).strip()), axis=1)
    df = df.sort_values("_contact_ok", ascending=False).drop_duplicates(subset=["Account Name"], keep="first")
    df = df.drop(columns=["_contact_ok"])
    return {row["Account Name"]: row for _, row in df.iterrows()}


def charger_bob(path: str) -> list[str]:
    df = pd.read_excel(path, header=11)
    df = df[df["Account Name"].notna()].copy()
    df = df[~df["Account Status  ↑"].isin({"Subtotal", "Total"})]
    return sorted({normaliser_nom(n) for n in df["Account Name"] if n and len(str(n)) > 2})


def est_dans_bob(nom: str, book_noms: list[str]) -> bool:
    n = normaliser_nom(nom)
    if not n or len(n) < 3:
        return False
    if n in book_noms:
        return True
    if len(n) < 8:
        return False
    match = process.extractOne(n, book_noms, scorer=fuzz.token_set_ratio)
    if match and match[1] >= FUZZY_THRESHOLD:
        return True
    return False


def trouver_compte_salesforce(nom_supabase: str, salesforce_noms: list[str]) -> tuple[str | None, float]:
    """Trouve le meilleur match Salesforce pour un nom Supabase."""
    match = process.extractOne(nom_supabase, salesforce_noms, scorer=fuzz.token_set_ratio)
    if match and match[1] >= FUZZY_THRESHOLD:
        return match[0], match[1]
    return None, 0.0


def charger_leads_supabase() -> list[dict]:
    """Recupere les leads Supabase interessants (score eleve + ouvertures recentes)."""
    url = f"{SUPABASE_URL}/rest/v1/leads"
    params = {
        "select": "nom,nom_legal,aliases,siren,code_naf,score,score_ca,score_sites,score_croissance,nb_etablissements,sites_ouverts_12m,derniere_ouverture,zone,chiffre_affaires,telephone,email,site_web,segment",
        "score": f"gte.{SCORE_MIN}",
        "sites_ouverts_12m": f"gt.{SITES_OUVERTS_MIN - 1}",
        "order": "score.desc",
        "limit": 1000,
    }
    resp = requests.get(url, params=params, headers=supabase_headers())
    resp.raise_for_status()
    return resp.json()


def main():
    base = Path(__file__).parent
    accounts_path = base / ACCOUNTS_FILE
    bob_path = base / BOB_FILE
    output_path = base / OUTPUT_CSV

    print("Chargement des comptes Salesforce...")
    sf_accounts = charger_comptes_salesforce(accounts_path)
    sf_noms = list(sf_accounts.keys())
    print(f"  {len(sf_accounts)} comptes uniques")

    print("Chargement du BOB...")
    book_noms = charger_bob(bob_path)
    print(f"  {len(book_noms)} noms uniques")

    print(f"Recuperation des leads Supabase (score >= {SCORE_MIN}, sites ouverts 12m >= {SITES_OUVERTS_MIN})...")
    leads = charger_leads_supabase()
    print(f"  {len(leads)} leads trouves")

    resultats = []
    for lead in leads:
        nom_supabase = lead.get("nom") or lead.get("nom_legal") or ""
        if not nom_supabase:
            continue

        # Essaie de matcher sur nom, puis nom_legal, puis aliases
        noms_a_tester = [nom_supabase]
        if lead.get("nom_legal") and lead["nom_legal"] != nom_supabase:
            noms_a_tester.append(lead["nom_legal"])
        if lead.get("aliases"):
            noms_a_tester.extend([a.strip() for a in str(lead["aliases"]).split(",") if a.strip()])

        meilleur_match = None
        meilleur_score = 0
        for nom_test in noms_a_tester:
            match, score = trouver_compte_salesforce(nom_test, sf_noms)
            if score > meilleur_score:
                meilleur_match = match
                meilleur_score = score

        if not meilleur_match:
            continue

        if est_dans_bob(meilleur_match, book_noms):
            continue

        sf = sf_accounts[meilleur_match]
        resultats.append({
            "Account Name Salesforce": meilleur_match,
            "Nom Prokitchens": nom_supabase,
            "Matching Score": round(meilleur_score, 1),
            "Score Prokitchens": lead.get("score"),
            "Score CA": lead.get("score_ca"),
            "Score Sites": lead.get("score_sites"),
            "Score Croissance": lead.get("score_croissance"),
            "SIREN": lead.get("siren"),
            "Code NAF": lead.get("code_naf"),
            "CA": lead.get("chiffre_affaires"),
            "Nb Etablissements": lead.get("nb_etablissements"),
            "Sites ouverts 12m": lead.get("sites_ouverts_12m"),
            "Derniere ouverture": lead.get("derniere_ouverture"),
            "Zone": lead.get("zone"),
            "Segment": lead.get("segment"),
            "Phone": sf.get("Phone"),
            "Mobile": sf.get("Mobile"),
            "Email": sf.get("Email"),
            "Account Owner": sf.get("Account Owner"),
            "Industry Segment": sf.get("Industry Segment"),
            "Kitchen Type": sf.get("Kitchen Type"),
        })

    print(f"\nComptes Salesforce interessants avec ouvertures recentes : {len(resultats)}")

    if not resultats:
        print("Aucun resultat.")
        return

    resultats.sort(key=lambda x: (x["Score Prokitchens"] or 0), reverse=True)

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=resultats[0].keys())
        writer.writeheader()
        writer.writerows(resultats)

    print(f"Fichier genere : {output_path}")


if __name__ == "__main__":
    main()
