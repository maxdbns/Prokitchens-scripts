"""
Enrichit les 27 comptes Salesforce precedemment identifies avec les donnees
du site Prokitchens (Supabase) : score, ouvertures recentes, CA, etc.
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


def charger_comptes_salesforce(path: str) -> pd.DataFrame:
    return pd.read_csv(path)


def charger_tous_leads_supabase() -> list[dict]:
    """Recupere les leads Supabase avec score >= 30 (648 comptes, gerable en memoire)."""
    url = f"{SUPABASE_URL}/rest/v1/leads"
    params = {
        "select": "nom,nom_legal,aliases,siren,code_naf,score,score_ca,score_sites,score_croissance,nb_etablissements,sites_ouverts_12m,derniere_ouverture,zone,chiffre_affaires,telephone,email,site_web,segment",
        "score": "gte.30",
        "order": "score.desc",
        "limit": 1000,
    }
    headers = {**supabase_headers(), "Range": "0-999"}
    resp = requests.get(url, params=params, headers=headers)
    resp.raise_for_status()
    return resp.json()


def trouver_meilleur_lead(nom: str, leads: list[dict]) -> tuple[dict | None, float]:
    meilleur = None
    meilleur_score = 0
    noms_a_tester = [nom]

    for lead in leads:
        noms_lead = [lead.get("nom") or "", lead.get("nom_legal") or ""]
        if lead.get("aliases"):
            noms_lead.extend([a.strip() for a in str(lead["aliases"]).split(",") if a.strip()])

        for nl in noms_lead:
            if not nl:
                continue
            score = fuzz.token_set_ratio(normaliser_nom(nom), normaliser_nom(nl))
            if score > meilleur_score:
                meilleur_score = score
                meilleur = lead

    if meilleur_score >= FUZZY_THRESHOLD:
        return meilleur, meilleur_score
    return None, 0.0


def main():
    base = Path(__file__).parent
    comptes_path = base / "comptes_interessants_hors_bob.csv"
    output_path = base / "comptes_interessants_hors_bob_avec_app.csv"

    print("Chargement des comptes Salesforce identifies...")
    df = charger_comptes_salesforce(comptes_path)
    print(f"  {len(df)} comptes")

    print("Recuperation de tous les leads Supabase...")
    leads = charger_tous_leads_supabase()
    print(f"  {len(leads)} leads charges")

    resultats = []
    for _, row in df.iterrows():
        nom = row["Account Name"]
        lead, score = trouver_meilleur_lead(nom, leads)

        out = dict(row)
        out["Matching App Score"] = round(score, 1) if score else 0
        if lead:
            out["Score App"] = lead.get("score")
            out["Score CA App"] = lead.get("score_ca")
            out["Score Sites App"] = lead.get("score_sites")
            out["Score Croissance App"] = lead.get("score_croissance")
            out["CA App"] = lead.get("chiffre_affaires")
            out["Nb Etablissements App"] = lead.get("nb_etablissements")
            out["Sites ouverts 12m App"] = lead.get("sites_ouverts_12m")
            out["Derniere ouverture App"] = lead.get("derniere_ouverture")
            out["Zone App"] = lead.get("zone")
            out["SIREN App"] = lead.get("siren")
            out["Code NAF App"] = lead.get("code_naf")
            out["Segment App"] = lead.get("segment")
        else:
            out["Score App"] = None
            out["Sites ouverts 12m App"] = None

        resultats.append(out)

    # Tri : d'abord ceux avec app data, puis par score
    resultats.sort(key=lambda x: (x["Score App"] is None, -(x["Score App"] or 0)))

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=resultats[0].keys())
        writer.writeheader()
        writer.writerows(resultats)

    print(f"\nFichier genere : {output_path}")

    # Stats
    avec_app = sum(1 for r in resultats if r["Score App"] is not None)
    avec_ouvertures = sum(1 for r in resultats if r.get("Sites ouverts 12m App") and r["Sites ouverts 12m App"] > 0)
    print(f"  {avec_app} comptes enrichis avec l'app")
    print(f"  {avec_ouvertures} comptes avec ouvertures recentes dans l'app")


if __name__ == "__main__":
    main()
