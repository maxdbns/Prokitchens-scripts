"""
Genere la liste des comptes Salesforce interessants qui ne sont pas dans le BOB.
Fichiers d'entree :
  - All accounts - France - incl. contacts-*.xlsx (tous les comptes Salesforce FR)
  - BOB.xlsx (comptes du Book of Business)
Sortie :
  - comptes_interessants_hors_bob.csv
"""

import csv
import re
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz, process

# Configuration
ACCOUNTS_FILE = "All accounts - France - incl. contacts-2026-07-23-14-47-11.xlsx"
BOB_FILE = "BOB.xlsx"
OUTPUT_CSV = "comptes_interessants_hors_bob.csv"

# Criteres "interessants"
ACCOUNT_TYPES_CIBLES = {"Enterprise", "Growth"}
INDUSTRY_SEGMENTS_CIBLES = {
    "QSR & Fast Casual",
    "Casual Dining & Brasserie",
    "Hotels & Resorts",
    "Bakery & Coffee",
}
FUZZY_THRESHOLD = 85

# Exclusions manuelles (comptes connus comme deja clients / dans le BOB sous un autre nom)
EXCLUSIONS_MANUELLES = {"Black & White burger"}

# Noms indiquant un compte de test a ignorer
MOTS_TEST = {"test", "zzz"}

# Prefixes telephoniques internationaux a exclure (hors France)
PREFIXES_INTERNATIONAUX = {
    "+44", "+34", "+1", "+32", "+31", "+39", "+49", "+41", "+43",
    "+351", "+352", "+353", "+44",
}

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
    """Nettoie un nom d'entreprise pour la comparaison."""
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


def normaliser_tel(phone) -> str:
    """Retourne les chiffres d'un numero de telephone (minimum 8 chiffres)."""
    if not phone:
        return ""
    digits = re.sub(r"\D", "", str(phone))
    if len(digits) >= 10 and digits.startswith("33"):
        digits = digits[2:]
    if len(digits) < 8:
        return ""
    return digits


def contact_valide(row: dict) -> bool:
    """Verifie qu'au moins un contact est renseigne (telephone ou email)."""
    phone = normaliser_tel(row.get("Phone", ""))
    mobile = normaliser_tel(row.get("Mobile", ""))
    email = str(row.get("Email", "")).strip()
    return bool(phone or mobile or email)


def est_francais(phone, mobile, email) -> tuple[bool, str]:
    """Verifie si les coordonnees indiquent un compte francais."""
    email = str(email).strip().lower()
    if email and (email.endswith(".co.uk") or email.endswith(".uk")):
        return False, "email UK"

    for num in [phone, mobile]:
        num = str(num).strip()
        if not num or num.lower() in ("nan", "none", "-", "", "/" * 10):
            continue

        # Avec prefixe international +
        if num.startswith("+"):
            prefix = num[:3]
            if prefix == "+33":
                continue
            if prefix in PREFIXES_INTERNATIONAUX:
                return False, f"telephone {prefix}"

        # Sans prefixe : on regarde les chiffres
        digits = re.sub(r"\D", "", num)
        if digits:
            if digits.startswith("33") or digits.startswith("0"):
                continue
            # Pays etrangers sans + (ex: 34 Espagne, 44 UK)
            if digits.startswith(("34", "44", "1", "32", "31", "39", "49", "41", "43", "351", "352", "353")):
                return False, f"telephone {digits[:3]}"

    return True, ""


def charger_comptes_salesforce(path: str) -> pd.DataFrame:
    """Charge le fichier de tous les comptes Salesforce FR."""
    df = pd.read_excel(path, header=9)
    # Garde uniquement les lignes avec un nom de compte
    df = df[df["Account Name"].notna()].copy()
    # Dedup par Account Name en gardant la meilleure ligne (avec telephone/email si possible)
    df["_contact_ok"] = df.apply(contact_valide, axis=1)
    df = df.sort_values("_contact_ok", ascending=False)
    df = df.drop_duplicates(subset=["Account Name"], keep="first")
    df = df.drop(columns=["_contact_ok"])
    return df.reset_index(drop=True)


def charger_bob(path: str) -> dict:
    """Charge le BOB et retourne un set de noms normalises."""
    df = pd.read_excel(path, header=11)
    df = df[df["Account Name"].notna()].copy()
    # Retire les lignes de sous-total / total
    df = df[~df["Account Status  ↑"].isin({"Subtotal", "Total"})]
    noms = set()
    for name in df["Account Name"]:
        n = normaliser_nom(name)
        if n and len(n) > 2:
            noms.add(n)
    return {"noms": sorted(noms), "df": df}


def est_dans_bob(nom: str, book_noms: list[str]) -> tuple[bool, str | None]:
    """Verifie si un compte est deja dans le BOB par matching de nom."""
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


def main():
    base = Path(__file__).parent
    accounts_path = base / ACCOUNTS_FILE
    bob_path = base / BOB_FILE
    output_path = base / OUTPUT_CSV

    print("Chargement des comptes Salesforce...")
    df_accounts = charger_comptes_salesforce(accounts_path)
    print(f"  {len(df_accounts)} comptes uniques charges")

    print("Chargement du BOB...")
    book = charger_bob(bob_path)
    book_noms = book["noms"]
    print(f"  {len(book_noms)} noms uniques dans le BOB")

    # Filtre interessant
    print("Filtrage des comptes interessants...")
    cibles = df_accounts[
        df_accounts["Account Type"].isin(ACCOUNT_TYPES_CIBLES) &
        df_accounts["Industry Segment"].isin(INDUSTRY_SEGMENTS_CIBLES)
    ].copy()
    print(f"  {len(cibles)} comptes correspondent aux criteres de base")

    cibles = cibles[cibles.apply(contact_valide, axis=1)]
    print(f"  {len(cibles)} avec contact valide")

    # Exclusions manuelles, test et non-France
    exclusions_manuelles = []
    exclusions_test = []
    exclusions_non_france = []
    cibles_france = []
    for _, row in cibles.iterrows():
        nom = row["Account Name"]
        nom_lower = str(nom).lower()
        if nom in EXCLUSIONS_MANUELLES or any(mot in nom_lower for mot in MOTS_TEST):
            exclusions_manuelles.append(nom)
            continue
        francais, motif = est_francais(row.get("Phone", ""), row.get("Mobile", ""), row.get("Email", ""))
        if not francais:
            exclusions_non_france.append((nom, motif))
            continue
        cibles_france.append(row)

    print(f"  {len(exclusions_manuelles)} exclus manuellement / test")
    print(f"  {len(exclusions_non_france)} exclus (non France)")

    # Exclusion BOB
    hors_bob = []
    dans_bob = 0
    for row in cibles_france:
        in_bob, match = est_dans_bob(row["Account Name"], book_noms)
        if in_bob:
            dans_bob += 1
            continue
        hors_bob.append({
            "Account Name": row["Account Name"],
            "Account Type": row["Account Type"],
            "Industry Segment": row["Industry Segment"],
            "Kitchen Type": row.get("Kitchen Type", ""),
            "Phone": row.get("Phone", ""),
            "Mobile": row.get("Mobile", ""),
            "Email": row.get("Email", ""),
            "Account Owner": row.get("Account Owner", ""),
            "Country": row.get("Country", ""),
        })

    print(f"  {dans_bob} exclus car deja dans le BOB")
    print(f"\nComptes interessants hors BOB : {len(hors_bob)}")

    if not hors_bob:
        print("Aucun compte a exporter.")
        return

    # Tri alphabetique
    hors_bob.sort(key=lambda x: str(x["Account Name"]).upper())

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=hors_bob[0].keys())
        writer.writeheader()
        writer.writerows(hors_bob)

    print(f"Fichier genere : {output_path}")


if __name__ == "__main__":
    main()
