import glob
import re
import pandas as pd


def extract_number(value):
    """Extrait le premier nombre entier d'une chaîne (loyer, surface)."""
    if pd.isna(value):
        return None
    text = str(value).replace(" ", " ").replace(" ", "").replace(",", ".")
    match = re.search(r"\d+(?:\.\d+)?", text)
    return float(match.group(0)) if match else None


def normalize_ville(ville):
    if pd.isna(ville):
        return ""
    return re.sub(r"\s+", " ", str(ville)).strip().upper()


def normalize_code_postal(cp):
    if pd.isna(cp):
        return ""
    digits = re.sub(r"\D", "", str(cp))
    # Code postal français : 5 chiffres, padding à gauche si 4 chiffres (ex: 4100 -> 04100)
    if len(digits) == 4:
        digits = "0" + digits
    return digits[:5] if len(digits) >= 5 else digits


def has_extraction(value):
    if pd.isna(value):
        return False
    text = str(value).strip()
    # Si c'est un nombre > 0, c'est une extraction. Si c'est "/" ou vide, ce n'est pas une extraction.
    if text in {"", "/", "NA", "N/A", "na", "n/a"}:
        return False
    num = extract_number(text)
    return num is not None and num > 0


def clean_profoods_csv(source_path: str, output_path: str) -> pd.DataFrame:
    """
    Nettoie le CSV exporté du Google Sheet ProFoods et génère un CSV standardisé
    avec les colonnes attendues par le notebook de matching.
    """
    df = pd.read_csv(source_path, header=[1, 2])

    out_rows = []
    for idx, row in df.iterrows():
        ville = normalize_ville(row[("Ville", "Unnamed: 2_level_1")])
        cp = normalize_code_postal(row[("Code postal", "Unnamed: 3_level_1")])
        surface = extract_number(row[("Unnamed: 11_level_0", "Surface bâtie totale (m²)")])
        loyer = extract_number(row[("Loyer attendu", "€HTHC/an")])
        extraction = has_extraction(row[("Extraction", "Diamètre (mm)")])
        adresse = str(row[("Adresse", "Unnamed: 5_level_1")]) if pd.notna(row[("Adresse", "Unnamed: 5_level_1")]) else ""
        gmaps = str(row[("Lien GMAPS", "Unnamed: 6_level_1")]) if pd.notna(row[("Lien GMAPS", "Unnamed: 6_level_1")]) else ""

        if not ville and not cp:
            continue

        id_bien = f"PF{idx:04d}"
        out_rows.append({
            "id_bien": id_bien,
            "adresse_ville": ville,
            "code_postal": cp,
            "surface_totale": int(surface) if surface else 0,
            "loyer_cible": loyer if loyer else 0.0,
            "a_une_extraction": extraction,
            "adresse_brute": adresse.strip(),
            "lien_gmaps": gmaps.strip(),
        })

    out_df = pd.DataFrame(out_rows)
    out_df.to_csv(output_path, index=False)
    print(f"[OK] {len(out_df)} biens nettoyés écrits dans {output_path}")
    return out_df


if __name__ == "__main__":
    sources = glob.glob("/zpool/one/maxime.debaugnies/profoods/*.csv")
    if not sources:
        raise FileNotFoundError("Aucun CSV ProFoods trouvé dans /zpool/one/maxime.debaugnies/profoods/")

    source = sources[0]
    output = "/zpool/one/maxime.debaugnies/data/biens_profoods.csv"
    clean_profoods_csv(source, output)
