import os
import sys
import pandas as pd
import requests

CSV_PATH = os.environ.get(
    "PATH_CSV_PROFOODS",
    "/zpool/one/maxime.debaugnies/data/biens_profoods.csv"
)
API_URL = os.environ.get(
    "PROFOODS_API_URL",
    "https://prokitchens-three.vercel.app/api/profoods/ingest"
)


def main() -> None:
    if not os.path.exists(CSV_PATH):
        print(f"[ERROR] CSV introuvable : {CSV_PATH}")
        sys.exit(1)

    df = pd.read_csv(CSV_PATH, dtype=str)

    # Normalisation des colonnes
    df.columns = [c.strip().lower().replace(" ", "_").replace("-", "_") for c in df.columns]

    required = ["id_bien", "adresse_ville", "code_postal", "surface_totale", "loyer_cible", "a_une_extraction"]
    for col in required:
        if col not in df.columns:
            print(f"[ERROR] Colonne manquante : {col}")
            sys.exit(1)

    df["adresse_ville"] = df["adresse_ville"].apply(lambda x: str(x).strip().upper() if pd.notna(x) else "")
    df["code_postal"] = df["code_postal"].apply(lambda x: "".join(filter(str.isdigit, str(x)))[:5] if pd.notna(x) else "")
    df["surface_totale"] = df["surface_totale"].apply(lambda x: int(float(x)) if pd.notna(x) and str(x).strip() else 0)
    df["loyer_cible"] = df["loyer_cible"].apply(lambda x: float(x) if pd.notna(x) and str(x).strip() else 0.0)
    df["a_une_extraction"] = df["a_une_extraction"].apply(
        lambda x: str(x).strip().lower() in {"1", "true", "oui", "yes", "vrai"}
        if pd.notna(x) else False
    )

    for col in ("adresse_brute", "lien_gmaps", "owner"):
        if col not in df.columns:
            df[col] = None

    biens = df[["id_bien", "adresse_ville", "code_postal", "surface_totale", "loyer_cible", "a_une_extraction", "adresse_brute", "lien_gmaps", "owner"]].to_dict(orient="records")
    for b in biens:
        for col in ("adresse_brute", "lien_gmaps", "owner"):
            if b[col] is not None and str(b[col]) == "nan":
                b[col] = None

    print(f"[INFO] Push de {len(biens)} biens vers {API_URL}")
    resp = requests.post(API_URL, json={"demandes": [], "biens": biens}, timeout=120)
    print(f"[INFO] Status : {resp.status_code}")
    try:
        print(resp.json())
    except Exception:
        print(resp.text)

    resp.raise_for_status()
    print("[OK] Biens ProFoods poussés en production.")


if __name__ == "__main__":
    main()
