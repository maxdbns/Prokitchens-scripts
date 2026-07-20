"""
Qualifie la liste de prospection en excluant le book of business
et en appliquant des filtres de qualité stricts.

Entrées :
  - leads_manquants_salesforce.csv : liste de prospection actuelle
  - Untitled spreadsheet - Sheet1.csv : export Salesforce du book of business

Sortie :
  - leads_qualifies.csv : leads nouveaux, ciblés et contactables
"""

import csv
import re
import sys
from rapidfuzz import fuzz, process

PROSPECTS_CSV = "leads_manquants_salesforce.csv"
BOOK_CSV = "Leads auto - Sheet1.csv"
OUTPUT_CSV = "leads_qualifies.csv"

# NAF cibles : restauration rapide (QSR) et traiteurs
NAF_CIBLES = {"56.10C", "56.21Z"}

# Score minimum pour la qualité
SCORE_MIN = 50

# Seuil de matching fuzzy sur le nom normalisé (0-100)
FUZZY_THRESHOLD = 85


def normaliser_nom(name):
    """Nettoie un nom d'entreprise pour la comparaison."""
    if not name:
        return ""
    name = str(name).upper()
    # Retire les prefixes geographiques/proprietaires type [PAR], (old), FR - PAR -
    name = re.sub(r"\[.*?\]", "", name)
    name = re.sub(r"\(OLD\)", "", name, flags=re.I)
    name = re.sub(r"\bOLD\b", "", name, flags=re.I)
    name = re.sub(r"\bFR\s*-\s*PAR\s*-?", "", name, flags=re.I)
    # Retire les formes juridiques courantes
    name = re.sub(
        r"\b(SAS|SASU|SARL|EURL|SCOP|SCIC|SA|SEMS|SEM|SNC|SCA)\b", "", name, flags=re.I
    )
    # Retire ponctuation et caracteres speciaux, remplace par espaces
    name = re.sub(r"[^A-Z0-9&\s]", " ", name)
    # Supprime les espaces multiples
    name = re.sub(r"\s+", " ", name).strip()
    return name


def normaliser_tel(phone):
    """Retourne les chiffres d'un numero de telephone (minimum 8 chiffres)."""
    if not phone:
        return ""
    digits = re.sub(r"\D", "", str(phone))
    # On garde le numero local (sans indicatif) pour matcher plus facilement
    if len(digits) >= 10 and digits.startswith("33"):
        digits = digits[2:]
    if len(digits) >= 11 and digits.startswith("1") and len(digits) == 11:
        # numero international US/UK etc, on garde tel quel
        pass
    if len(digits) < 8:
        return ""
    return digits


def charger_book_of_business(path):
    """Charge et nettoie le book of business. Retourne un dict avec noms et telephones."""
    noms = set()
    telephones = set()

    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            account = normaliser_nom(row.get("Account Name", ""))
            if account and len(account) > 2:
                noms.add(account)

            for col in ("Phone", "Mobile"):
                tel = normaliser_tel(row.get(col, ""))
                if tel:
                    telephones.add(tel)

    return {"noms": sorted(noms), "telephones": telephones}


def est_dans_book_of_business(nom, telephone, book):
    """Vérifie si un lead est deja dans le book of business."""
    nom_norm = normaliser_nom(nom)
    if not nom_norm or len(nom_norm) < 3:
        return False

    # Match exact normalise
    if nom_norm in book["noms"]:
        return True

    # Pour les noms courts, on ne fait pas de fuzzy/sous-chaine (trop de faux positifs)
    if len(nom_norm) < 8:
        return False

    # Fuzzy match strict sur l'ensemble des tokens (insensible a l'ordre, meilleur pour les noms d'entreprise)
    match = process.extractOne(nom_norm, book["noms"], scorer=fuzz.token_set_ratio)
    if match and match[1] >= FUZZY_THRESHOLD:
        return True

    # Match par telephone
    tel_norm = normaliser_tel(telephone)
    if tel_norm and tel_norm in book["telephones"]:
        return True

    return False


def site_web_valide(url):
    """Vérifie que le site web n'est pas vide et semble valide."""
    if not url:
        return False
    url = str(url).strip().lower()
    if url in ("nan", "n/a", "-", "none", ""):
        return False
    return url.startswith("http://") or url.startswith("https://")


def telephone_valide(phone):
    """Vérifie qu'un telephone contient au moins 8 chiffres."""
    if not phone:
        return False
    digits = re.sub(r"\D", "", str(phone))
    return len(digits) >= 8


def qualifier():
    print("Chargement du book of business...")
    book = charger_book_of_business(BOOK_CSV)
    print(f"  {len(book['noms'])} noms uniques")
    print(f"  {len(book['telephones'])} telephones uniques")

    with open(PROSPECTS_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        leads = list(reader)

    print(f"\nLeads en entree : {len(leads)}")

    gardes = []
    rejets = {
        "hors_naf": 0,
        "sans_contact": 0,
        "score_bas": 0,
        "dans_book": 0,
    }

    for lead in leads:
        naf = lead.get("NAF", "").strip()
        score_str = lead.get("Score", "0") or "0"
        try:
            score = int(float(score_str))
        except ValueError:
            score = 0

        nom = lead.get("Nom", "")
        telephone = lead.get("Telephone", "")
        site = lead.get("Site Web", "")

        # Filtre NAF
        if naf not in NAF_CIBLES:
            rejets["hors_naf"] += 1
            continue

        # Filtre contact
        if not (telephone_valide(telephone) or site_web_valide(site)):
            rejets["sans_contact"] += 1
            continue

        # Filtre score
        if score < SCORE_MIN:
            rejets["score_bas"] += 1
            continue

        # Exclusion book of business
        if est_dans_book_of_business(nom, telephone, book):
            rejets["dans_book"] += 1
            continue

        gardes.append(lead)

    print("\n--- Rejets ---")
    for k, v in rejets.items():
        print(f"  {k}: {v}")
    print(f"\nLeads qualifies : {len(gardes)}")

    if not gardes:
        print("Aucun lead qualifie. Abandon.")
        sys.exit(0)

    # Tri par score decroissant
    gardes.sort(key=lambda x: int(float(x.get("Score", "0") or "0")), reverse=True)

    # Ecriture
    with open(OUTPUT_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=gardes[0].keys())
        writer.writeheader()
        writer.writerows(gardes)

    print(f"\nFichier genere : {OUTPUT_CSV}")

    print("\nTop 10 des leads qualifies :")
    for lead in gardes[:10]:
        print(
            f"  Score {lead.get('Score','?'):>3} | {lead.get('Nom','?')[:40]:<40} | "
            f"{lead.get('Telephone','')[:20]:<20} | {lead.get('Site Web','')[:35]:<35} | "
            f"NAF {lead.get('NAF','?')} | {lead.get('Ville','?')}"
        )


if __name__ == "__main__":
    qualifier()
