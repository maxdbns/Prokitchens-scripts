"""
Liste des leads a spots-check manuellement dans Salesforce/BOB.
Seuls les noms vraiment suspects sont gardes : sigles, noms de ville+chiffre,
holdings, operateurs, noms de personnes ou generiques ambigus.
"""
import csv
import re
from check_bob import normaliser_nom

INPUT = "data/LEADS_PROKITCHES_FINAL.csv"
OUTPUT = "data/spot_check_bob.csv"

SUSPECT_PATTERNS = [
    r"\d+$",                          # se termine par un chiffre
    r"\([A-Z0-9!]+\)",               # initiales/symboles entre parentheses
    r"\b[A-Z]{2,6}\s+GESTION\b",     # sigle + gestion
    r"\bMFCO\b", r"\bHVM\b",         # sigles techniques
    r"\bALIMENTATION\b", r"\bRESTAURANTS\s+BISTROT\b",
    r"\bBERRI\b", r"\bSAINT\s+HONORE\b", r"\bCITOYENS\b",
    r"\bEXPLOITATION\b", r"\bRETAIL\b", r"\bTECH\b",
    r"\bMENDES\b", r"\bJANIAUD\b", r"\bBENYOUNES\b", r"\bLANOIX\b", r"\bBECKER\b",
    r"\bGARES\b", r"\bHOPITAL\b", r"\bFINANCES\b", r"\bINVESTISSEMENTS\b",
]

EXPLICIT_OK = {
    "BAGEL CHEF", "CAFE KITSUNE", "TPEB FOOD", "K2 KITCHEN",
    "I-LUNCH", "GROM", "RESILIANS", "TRIAXE", "THUSAKI", "SASU CHOPSTICKS",
    "PEGAST", "LABEL FERME", "NOMAS FRANCE", "KENTARINE", "L ESCARGOT",
    "LE CUBE", "EL CAPITAN", "J.M", "BBT PARIS", "MINICAFE", "GROUPE MTG",
    "KOL", "TFB RESEAU", "B2S", "GN FRANCE 2022", "TPEB FOOD", "DOUGHNUTS",
    "LA FAMILLE KLEBER", "ELYSEE CAVIAR", "LA TABLE DE CANA", "AUX DELICES DES ANTILLES",
    "WING KITCHENS", "LA RECETTE FRANCE", "LES BOLS-CHOISEUL", "WOK UP", "DEEPKITCHEN",
    "SUWOK", "LE GAIGNE", "DIMA POULET", "LAMN SUSHI", "BABOOTEA", "THE ALLEY",
    "FOODOJAP", "FOODOBAR", "BRAVO PASTA", "YORA PARIS", "STRADINA", "MOCA", "GO EAT",
    "CRUNCHEESE", "YOICHI", "QUATRE SOEURS", "MS PATISSERIE", "ART DE VIVRE",
    "FEELNFOOD", "FOOD EMBASSY", "REST INOV", "REGAL DES ILES", "COMPAGNIE ABDAOUI",
    "KROUSTY", "BALUCHON", "AMUNDSEN", "COMPTOIR BELGE", "D JAWA", "SUSHI LE 1984",
    "LES 4 BAMBOUS", "GIVREE BOUTIQUES", "CHAUDEMANCHE", "GRAIN DE MOUTARDE",
    "DELEEV", "ENTRE PARENTHESE", "BFC", "SPINACH", "COTTI COFFEE",
}


def is_suspect(nom):
    n = normaliser_nom(nom)
    for ok in EXPLICIT_OK:
        if ok in n or n in ok:
            return False
    for pat in SUSPECT_PATTERNS:
        if re.search(pat, n, re.I):
            return True
    tokens = n.split()
    # Nom court (1-2 mots) sans site web = risque
    if len(tokens) <= 2:
        return True
    return False


with open(INPUT, "r", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

spot = [r for r in rows if is_suspect(r.get("Nom", ""))]

with open(OUTPUT, "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=rows[0].keys() if rows else [])
    writer.writeheader()
    writer.writerows(spot)

print(f"{len(spot)} leads suspects a spots-check dans Salesforce")
print(f"Fichier : {OUTPUT}")
