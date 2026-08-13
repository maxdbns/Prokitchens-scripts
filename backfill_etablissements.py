import os, urllib.request, urllib.parse, json, time
from run_guard import warn_if_zero

URL = os.environ["NEXT_PUBLIC_SUPABASE_URL"]
KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
INSEE_KEY = os.environ["INSEE_API_KEY"]

if not URL or not KEY or not INSEE_KEY:
    raise EnvironmentError("NEXT_PUBLIC_SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY and INSEE_API_KEY must be set")


def supabase_rpc(function: str, params: dict) -> any:
    body = json.dumps(params).encode()
    req = urllib.request.Request(f"{URL}/rest/v1/rpc/{function}", data=body, headers={
        "apikey": KEY,
        "Authorization": f"Bearer {KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode()
            return json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        print(f"Supabase RPC {function} HTTP {e.code}")
        print(e.read().decode())
        raise


def supabase_select_existing_sirets(sirets: list[str]) -> set[str]:
    if not sirets:
        return set()
    # Supabase IN filter limit is large; split if needed
    chunks = [sirets[i:i + 500] for i in range(0, len(sirets), 500)]
    existing: set[str] = set()
    for chunk in chunks:
        siret_list = ",".join(chunk)
        req = urllib.request.Request(f"{URL}/rest/v1/etablissements?select=siret&siret=in.({siret_list})", headers={
            "apikey": KEY,
            "Authorization": f"Bearer {KEY}",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            for row in data:
                existing.add(row["siret"])
    return existing


def supabase_insert(rows: list) -> None:
    if not rows:
        return
    body = json.dumps(rows).encode()
    req = urllib.request.Request(f"{URL}/rest/v1/etablissements", data=body, headers={
        "apikey": KEY,
        "Authorization": f"Bearer {KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            return
    except urllib.error.HTTPError as e:
        print(f"Supabase insert HTTP {e.code}")
        print(e.read().decode())
        raise


def supabase_update_etab(row: dict) -> None:
    siret = row["siret"]
    body = json.dumps({
        "lead_id": row["lead_id"],
        "siren": row["siren"],
        "nom": row["nom"],
        "adresse": row["adresse"],
        "ville": row["ville"],
        "code_postal": row["code_postal"],
        "date_creation": row["date_creation"],
        "code_naf": row["code_naf"],
        "est_siege": row["est_siege"],
    }).encode()
    req = urllib.request.Request(f"{URL}/rest/v1/etablissements?siret=eq.{siret}", data=body, headers={
        "apikey": KEY,
        "Authorization": f"Bearer {KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }, method="PATCH")
    try:
        with urllib.request.urlopen(req) as resp:
            return
    except urllib.error.HTTPError as e:
        print(f"Supabase update HTTP {e.code} for siret {siret}")
        print(e.read().decode())
        raise


def supabase_batch_upsert(rows: list, max_retries: int = 3) -> None:
    """Upsert en masse via PostgREST on_conflict=siret (insert + update en 1 requête).
    La base déclenche des triggers coûteux par ligne, on découpe donc en petits
    paquets pour éviter le statement timeout de Supabase."""
    if not rows:
        return

    chunk_size = 10
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i:i + chunk_size]
        body = json.dumps(chunk).encode()
        req = urllib.request.Request(f"{URL}/rest/v1/etablissements?on_conflict=siret", data=body, headers={
            "apikey": KEY,
            "Authorization": f"Bearer {KEY}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Prefer": "return=minimal,resolution=merge-duplicates",
        }, method="POST")
        last_error = None
        for attempt in range(max_retries):
            try:
                with urllib.request.urlopen(req) as resp:
                    break
            except urllib.error.HTTPError as e:
                last_error = e
                error_text = e.read().decode()
                print(f"Supabase batch upsert chunk {i//chunk_size + 1} HTTP {e.code} (attempt {attempt + 1})")
                print(error_text)
                if "57014" in error_text and attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise
        if last_error:
            raise last_error


def supabase_update_lead(lead_id: int, updates: dict) -> None:
    body = json.dumps(updates).encode()
    req = urllib.request.Request(f"{URL}/rest/v1/leads?id=eq.{lead_id}", data=body, headers={
        "apikey": KEY,
        "Authorization": f"Bearer {KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }, method="PATCH")
    try:
        with urllib.request.urlopen(req) as resp:
            return
    except urllib.error.HTTPError as e:
        print(f"Supabase update lead HTTP {e.code}")
        print(e.read().decode())
        raise


def insee_fetch_sirets(sirens: list[str]) -> list:
    # Integration key does not support AND filters; use OR only.
    siren_query = " OR ".join([f"siren:{s}" for s in sirens])
    q = f"({siren_query})"
    results: list = []
    debut = 0
    while True:
        params = urllib.parse.urlencode({"q": q, "nombre": "1000", "debut": str(debut)})
        url = f"https://api.insee.fr/api-sirene/3.11/siret?{params}"
        req = urllib.request.Request(url, headers={
            "X-INSEE-Api-Key-Integration": INSEE_KEY,
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                break
            print(f"INSEE HTTP {e.code} on {url}")
            print(e.read().decode())
            raise

        etabs = data.get("etablissements", [])
        if not etabs:
            break
        results.extend(etabs)
        total = data.get("header", {}).get("total", 0)
        debut += 1000
        if debut >= total:
            break
        time.sleep(0.5)
    return results


def build_adresse(adr: dict) -> str:
    parts = [adr.get("numeroVoieEtablissement"), adr.get("typeVoieEtablissement"), adr.get("libelleVoieEtablissement")]
    return " ".join([str(p) for p in parts if p]) or ""


def parse_enseignes(raw_etabs: list) -> dict:
    result: dict = {}
    for e in raw_etabs:
        siren = e.get("siren", "")
        adresse = e.get("adresseEtablissement", {})
        periode = (e.get("periodesEtablissement") or [{}])[0]
        unite = e.get("uniteLegale", {})
        date_creation = e.get("dateCreationEtablissement", "")
        enseigne_nom = (
            periode.get("enseigne1Etablissement")
            or periode.get("enseigne2Etablissement")
            or periode.get("enseigne3Etablissement")
            or periode.get("denominationUsuelleEtablissement")
            or ""
        )
        nom_legal = (
            unite.get("denominationUniteLegale")
            or f"{unite.get('prenomUsuelUniteLegale', '')} {unite.get('nomUniteLegale', '')}".strip()
            or "Inconnu"
        )
        etab = {
            "siret": e.get("siret", ""),
            "nom": enseigne_nom or nom_legal,
            "adresse": build_adresse(adresse),
            "ville": adresse.get("libelleCommuneEtablissement", ""),
            "code_postal": adresse.get("codePostalEtablissement", ""),
            "date_creation": date_creation,
            "code_naf": periode.get("activitePrincipaleEtablissement", ""),
            "est_siege": e.get("etablissementSiege") is True,
        }
        if siren not in result:
            result[siren] = {"nom": enseigne_nom or nom_legal, "etablissements": [etab]}
        else:
            result[siren]["etablissements"].append(etab)
    return result


def main():
    total_repaired = 0
    total_upserted = 0
    iteration = 0

    while True:
        iteration += 1
        print(f"[backfill] iteration {iteration}...")

        mismatches = supabase_rpc("get_leads_with_etab_mismatch", {"p_limit": 20})
        if not mismatches:
            print("[backfill] no more mismatches, stopping")
            break

        sirens = [m["siren"] for m in mismatches]
        lead_id_by_siren = {m["siren"]: m["lead_id"] for m in mismatches}
        print(f"[backfill] fetching INSEE for {len(sirens)} sirens...")

        raw_etabs = insee_fetch_sirets(sirens)
        print(f"[backfill] got {len(raw_etabs)} raw etabs")
        enseignes = parse_enseignes(raw_etabs)
        found_sirens = set(enseignes.keys())
        print(f"[backfill] parsed {len(enseignes)} enseignes")

        all_etabs: list = []
        for siren, enseigne in enseignes.items():
            lead_id = lead_id_by_siren[siren]
            for etab in enseigne["etablissements"]:
                if not etab["siret"]:
                    continue
                all_etabs.append({
                    "lead_id": lead_id,
                    "siren": siren,
                    "siret": etab["siret"],
                    "nom": etab["nom"] or enseigne["nom"] or "Inconnu",
                    "adresse": etab["adresse"] or None,
                    "ville": etab["ville"],
                    "code_postal": etab["code_postal"],
                    "date_creation": etab["date_creation"] or None,
                    "code_naf": etab["code_naf"] or None,
                    "est_siege": etab["est_siege"],
                })

        print(f"[backfill] upserting {len(all_etabs)} etablissements...")
        # Upsert found etablissements in chunks
        for i in range(0, len(all_etabs), 500):
            chunk = all_etabs[i:i + 500]
            print(f"[backfill] upsert chunk {i//500 + 1}/{(len(all_etabs)+499)//500} ({len(chunk)} rows)")
            supabase_batch_upsert(chunk)
            print(f"[backfill] chunk {i//500 + 1} done")

        # Mark not-found SIRENs as 0 establishments to avoid infinite loop
        not_found = [m for m in mismatches if m["siren"] not in found_sirens]
        for nf in not_found:
            supabase_update_lead(nf["lead_id"], {
                "nb_etablissements": 0,
                "derniere_ouverture": None,
                "sites_ouverts_12m": 0,
                "updated_at": "now()",
            })

        print(f"[backfill] refreshing aggregates for {len(mismatches)} leads...")
        lead_ids = [m["lead_id"] for m in mismatches]
        for i in range(0, len(lead_ids), 10):
            chunk = lead_ids[i:i + 10]
            for attempt in range(3):
                try:
                    supabase_rpc("refresh_lead_aggregates", {"p_lead_ids": chunk})
                    break
                except Exception as e:
                    if attempt < 2:
                        print(f"[backfill] aggregate chunk {i//10+1} failed (attempt {attempt+1}), retrying...")
                        time.sleep(2 ** attempt)
                    else:
                        print(f"[backfill] aggregate chunk {i//10+1} failed after 3 attempts: {e}")
            time.sleep(1)
        print(f"[backfill] aggregates refreshed")

        repaired = len(mismatches)
        upserted = len(all_etabs)
        total_repaired += repaired
        total_upserted += upserted
        print(f"[backfill] repaired={repaired}, upserted={upserted}, not_found={len(not_found)}")

        time.sleep(3)

    print(f"[backfill] done. total repaired={total_repaired}, total upserted={total_upserted}")
    warn_if_zero("Backfill : établissements upsertés", total_upserted)


if __name__ == "__main__":
    main()
