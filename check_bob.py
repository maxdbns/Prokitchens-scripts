"""
Verifie si une liste de noms de chaines est presente dans le BOB Salesforce.
Matching defensif : privilegie la precision (eviter les faux positifs).
"""

import csv
import re
from rapidfuzz import fuzz, process

import os

BOOK_CSV = "data/Leads auto - Sheet1.csv"
NAMES_FILE = "docs/chaines_candidates.txt"
OUTPUT_CSV = "data/chaines_hors_bob.csv"

MOTS_VIDES = {"LE", "LA", "LES", "DU", "DE", "DES", "ET", "EN", "A", "AU", "AUX", "FR", "FRANCE", "SAS", "SARL", "SASU", "EURL", "SCOP", "SCIC", "SA", "SEMS", "SEM", "SNC", "SCA"}
MOTS_GENERIQUES = {
    "SUSHI", "BURGER", "TACOS", "CHICKEN", "POULET", "PIZZA", "PASTA",
    "WOK", "BOWL", "DIM", "SUM", "RAMEN", "NOODLE", "BURRITOS", "BAGEL",
    "FRESH", "TIME", "FACTORY", "WINGS", "ROOSTERS", "BAO", "PITA", "KEBAB",
    "CROUSTY", "SNACK", "CAFE", "COFFEE", "RESTO", "RESTAURANT", "GRILL",
    "FAST", "FOOD", "GO", "GOOD", "MISTER", "MASTER", "ORIGINAL", "TASTY",
    "NEW", "KING", "AVENUE", "DELI", "DAILY", "MARKET", "SHOP", "BAR",
    "HOUSE", "LAB", "POKE", "BISTROT", "COMPTOIR", "BISTRO", "TABLE",
    "DELICES", "KITCHEN", "LUNCH", "BRUNCH", "DINER", "BUFFET", "PATISSERIE",
    "BOULANGERIE", "BOULANGE", "SANDWICH", "SALON", "THE", "CHOCOLAT",
    "GOURMAND", "GOURMET", "CROISSANTERIE", "PAIN", "VIENNOISERIE", "BREAD",
    "WAY", "GOODIES", "BUN", "MIAN", "FAN", "NANA", "MAMA", "PAPA", "MAMIE",
    "MAMAN", "PAPI", "BABY", "MISTER", "MISS", "KING", "QUEEN", "BURGER",
    "STREET", "CORNER", "PLACE", "EAT", "EATS", "FAMILY", "FRIENDS", "HOUSE",
    "CITY", "PARIS", "LYON", "MARSEILLE", "BORDEAUX", "LILLE", "NANTES",
    "STRASBOURG", "TOULOUSE", "NICE", "MONTPELLIER", "RENNES", "TOURS",
    "FRANCHIS", "FRANCHISE", "GROUPE", "HOLDING", "RESTAURANTS", "SYSTEM",
    "BISTRO", "CAFE", "RESTO", "FOOD", "TRUCK", "KITCHEN", "BAR", "DELI",
}


def normaliser_nom(name):
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


def _telecharger_csv_supabase():
    """Télécharge le CSV BOB depuis Supabase Storage si absent localement."""
    supabase_url = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "")
    supabase_key = os.environ.get("SUPABASE_API_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not supabase_url or not supabase_key:
        return False
    try:
        import requests
        url = f"{supabase_url}/storage/v1/object/public/data/Leads%20auto%20-%20Sheet1.csv"
        resp = requests.get(url, headers={"Authorization": f"Bearer {supabase_key}"}, timeout=30)
        if resp.status_code == 200:
            os.makedirs("data", exist_ok=True)
            with open(BOOK_CSV, "wb") as f:
                f.write(resp.content)
            return True
    except Exception:
        pass
    return False


def charger_book():
    if not os.path.exists(BOOK_CSV):
        if not _telecharger_csv_supabase():
            print(f"[check_bob] WARNING: {BOOK_CSV} introuvable et téléchargement Supabase échoué — filtrage BOB désactivé")
            return []
    noms = set()
    with open(BOOK_CSV, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            n = normaliser_nom(row.get("Account Name", ""))
            if n and len(n) > 2:
                noms.add(n)
    return sorted(noms)


def tokens_significatifs(name):
    return [t for t in normaliser_nom(name).split() if t and t not in MOTS_VIDES and len(t) > 2]


def tokens_distinctifs(name):
    return [t for t in tokens_significatifs(name) if t not in MOTS_GENERIQUES]


def token_in_name(token, name_tokens):
    """Verifie si token est present exactement dans name_tokens."""
    return token in name_tokens


def est_dans_bob(nom, book_noms, threshold=80):
    n = normaliser_nom(nom)
    if not n or len(n) < 3:
        return False, None

    # Exact
    if n in book_noms:
        return True, n

    tokens_c = tokens_significatifs(nom)
    distinctifs_c = tokens_distinctifs(nom)

    # 1. Recherche de noms BOB contenant tous les tokens distinctifs du candidat
    if distinctifs_c:
        for m in book_noms:
            m_tokens = set(tokens_significatifs(m))
            if all(token_in_name(d, m_tokens) for d in distinctifs_c):
                # Si un seul token distinctif, verifier le score global pour eviter les faux positifs
                if len(distinctifs_c) == 1:
                    score = fuzz.token_set_ratio(n, m)
                    if score >= 75:
                        return True, f"{m} ({score:.0f})"
                else:
                    return True, m

    # 2. Fuzzy matching pour les noms sans token distinctif (tres generiques)
    if not distinctifs_c:
        match = process.extractOne(n, book_noms, scorer=fuzz.token_set_ratio)
        if match and match[1] >= 90:
            m = match[0]
            m_tokens = set(tokens_significatifs(m))
            communs = [t for t in tokens_c if token_in_name(t, m_tokens)]
            if len(communs) >= max(1, len(tokens_c) - 1):
                return True, f"{m} ({match[1]:.0f})"
        return False, None

    # 3. Fuzzy fallback : au moins un token distinctif en commun et score eleve
    match = process.extractOne(n, book_noms, scorer=fuzz.token_set_ratio)
    if match and match[1] >= threshold:
        m = match[0]
        m_tokens = set(tokens_significatifs(m))
        if any(token_in_name(d, m_tokens) for d in distinctifs_c):
            return True, f"{m} ({match[1]:.0f})"

    return False, None


def main():
    book = charger_book()
    print(f"{len(book)} noms uniques dans le BOB")

    with open(NAMES_FILE, "r", encoding="utf-8") as f:
        chaines = [line.strip() for line in f if line.strip()]

    hors_bob = []
    for chaine in chaines:
        in_bob, match = est_dans_bob(chaine, book)
        if in_bob:
            print(f"  [BOB] {chaine} -> {match}")
        else:
            hors_bob.append({"chaine": chaine})
            print(f"  [HORS BOB] {chaine}")

    with open(OUTPUT_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["chaine"])
        writer.writeheader()
        writer.writerows(hors_bob)

    print(f"\n{len(hors_bob)} chaines hors BOB")
    print(f"Fichier : {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
