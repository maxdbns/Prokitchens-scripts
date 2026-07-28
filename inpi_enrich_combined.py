"""
Enrichissement INPI combiné — financier + dirigeants.
Async / multithreadé avec un quota journalier partagé.
"""

import asyncio
import aiohttp
from datetime import datetime

# ─── Config ───
INPI_USERNAME = "maxime.debaugnies@cloudkitchens.com"
INPI_PASSWORD = "Thomas36130!"
INPI_BASE_URL = "https://registre-national-entreprises.inpi.fr/api"

SUPABASE_URL = "https://hxjryfaakdpwfgseirik.supabase.co"
SUPABASE_API_KEY = "sb_publishable_a7xpn8srwByQrW1rXwpdlw_eQnwAoHT"
SUPABASE_TABLE = "leads"

DAILY_QUOTA = 9500
MAX_WORKERS = 1
REQUEST_DELAY = 0.5
LOG_FILE = "/zpool/one/maxime.debaugnies/logs/inpi_enrich_combined.log"

ROLE_LABELS = {
    "53": "Président",
    "65": "Directeur général",
    "10": "Gérant",
    "11": "Co-gérant",
    "16": "Président du conseil d'administration",
    "17": "Administrateur",
}


def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


async def inpi_login(session):
    async with session.post(
        f"{INPI_BASE_URL}/sso/login",
        json={"username": INPI_USERNAME, "password": INPI_PASSWORD},
        headers={"Content-Type": "application/json"},
        timeout=aiohttp.ClientTimeout(total=30),
    ) as resp:
        resp.raise_for_status()
        data = await resp.json()
        log("Connecté à l'API INPI")
        return data["token"]


async def fetch_count(session, params):
    count_params = {**params, "limit": 1}
    async with session.get(
        f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}",
        params=count_params,
        headers={
            "apikey": SUPABASE_API_KEY,
            "Authorization": f"Bearer {SUPABASE_API_KEY}",
            "Accept": "application/json",
            "Prefer": "count=exact",
        },
        timeout=aiohttp.ClientTimeout(total=30),
    ) as resp:
        resp.raise_for_status()
        return int(resp.headers.get("content-range", "0-0/0").split("/")[-1])


async def fetch_leads(session, params, limit, offset=0):
    fetch_params = {
        **params,
        "select": "siren,nom,ville",
        "limit": limit,
        "offset": offset,
    }
    async with session.get(
        f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}",
        params=fetch_params,
        headers={
            "apikey": SUPABASE_API_KEY,
            "Authorization": f"Bearer {SUPABASE_API_KEY}",
            "Accept": "application/json",
        },
        timeout=aiohttp.ClientTimeout(total=30),
    ) as resp:
        resp.raise_for_status()
        return await resp.json()


def parse_montant(val):
    if not val:
        return None
    try:
        return int(val.strip())
    except (ValueError, TypeError):
        return None


def extract_financial_data(bilan_saisi):
    """Extrait CA, RN et date de clôture d'un bilan saisi."""
    bilan = bilan_saisi.get("bilanSaisi", {}).get("bilan", {})
    identite = bilan.get("identite", {})
    date_cloture = identite.get("dateClotureExercice", "")

    ca = None
    resultat_net = None

    for page in bilan.get("detail", {}).get("pages", []):
        for liasse in page.get("liasses", []):
            code = liasse.get("code", "")
            if code == "FL":
                ca = parse_montant(liasse.get("m3") or liasse.get("m1"))
            elif code == "FJ" and ca is None:
                ca = parse_montant(liasse.get("m3") or liasse.get("m1"))
            elif code == "HN":
                resultat_net = parse_montant(liasse.get("m1"))

    if ca is None and resultat_net is None:
        return None

    return {
        "chiffre_affaires": ca,
        "resultat_net": resultat_net,
        "date_cloture_bilan": date_cloture,
    }


def extract_best_financial_data(bilans_saisis):
    """
    Parcourt tous les bilans publics non supprimés et retourne le plus récent
    qui contient un CA ou un résultat net (point 1 : ne pas s'arrêter au premier).
    """
    candidates = []
    for bs in bilans_saisis:
        if bs.get("confidentiality") != "Public" or bs.get("deleted", False):
            continue
        data = extract_financial_data(bs)
        if data and (data["chiffre_affaires"] is not None or data["resultat_net"] is not None):
            candidates.append(data)

    if not candidates:
        return None

    # Trie par date de clôture décroissante ; les dates vides passent en dernier
    def sort_key(d):
        return d.get("date_cloture_bilan") or "0000-00-00"

    candidates.sort(key=sort_key, reverse=True)
    return candidates[0]


def extract_dirigeant(data):
    pouvoirs = (
        data.get("formality", {})
        .get("content", {})
        .get("personneMorale", {})
        .get("composition", {})
        .get("pouvoirs", [])
    )

    for pouvoir in pouvoirs:
        individu = pouvoir.get("individu", {})
        desc = individu.get("descriptionPersonne", {})
        nom = desc.get("nom")
        prenoms = desc.get("prenoms", [])
        role_code = pouvoir.get("roleEntreprise", "")

        if nom and prenoms:
            return {
                "dirigeant_nom": nom.title(),
                "dirigeant_prenom": prenoms[0].title(),
                "dirigeant_role": ROLE_LABELS.get(role_code, role_code),
            }

    return None


async def inpi_request_with_retry(session, url, stats, token_lock, token_holder):
    for attempt in range(3):
        used_token = token_holder["token"]
        try:
            async with session.get(
                url,
                headers={"Authorization": f"Bearer {used_token}"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                stats["api_calls"] += 1

                if resp.status == 401:
                    async with token_lock:
                        if token_holder["token"] == used_token:
                            token_holder["token"] = await inpi_login(session)
                    continue

                if resp.status == 429:
                    log("  Rate limit INPI, pause 60s...")
                    await asyncio.sleep(60)
                    continue

                if resp.status == 404:
                    return None

                if resp.status != 200:
                    return None

                return await resp.json()
        except aiohttp.ClientError as e:
            log(f"  Erreur réseau INPI {url}: {e}")
            if attempt < 2:
                await asyncio.sleep(5 + attempt * 5)
                continue
            return None

    return None


async def get_financial_data(session, siren, stats, token_lock, token_holder):
    data = await inpi_request_with_retry(
        session, f"{INPI_BASE_URL}/companies/{siren}/attachments", stats, token_lock, token_holder
    )
    if not data:
        return None

    return extract_best_financial_data(data.get("bilansSaisis", []))


async def get_dirigeant(session, siren, stats, token_lock, token_holder):
    data = await inpi_request_with_retry(
        session, f"{INPI_BASE_URL}/companies/{siren}", stats, token_lock, token_holder
    )
    if not data:
        return None
    return extract_dirigeant(data)


async def patch_lead(session, siren, patch):
    try:
        async with session.patch(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}?siren=eq.{siren}",
            headers={
                "apikey": SUPABASE_API_KEY,
                "Authorization": f"Bearer {SUPABASE_API_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json=patch,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            return resp.status in (200, 204)
    except aiohttp.ClientError as e:
        log(f"  Erreur patch SIREN {siren}: {e}")
        return False


async def worker(name, queue, session, stats, token_lock, token_holder, stop_event):
    while True:
        task = await queue.get()
        if task is None:
            queue.task_done()
            break

        if stop_event.is_set():
            queue.task_done()
            break

        task_type, lead = task
        siren = lead["siren"]
        nom = lead.get("nom", "?")[:45]

        try:
            await asyncio.sleep(REQUEST_DELAY)

            if task_type == "financial":
                data = await get_financial_data(session, siren, stats, token_lock, token_holder)
                now = datetime.now().isoformat()

                if data:
                    # Point 2 : enriched_inpi=true uniquement quand on a réellement des données
                    patch = {
                        "enriched_inpi": True,
                        "inpi_attempted_at": now,
                    }
                    if data["chiffre_affaires"] is not None:
                        patch["chiffre_affaires"] = data["chiffre_affaires"]
                    if data["resultat_net"] is not None:
                        patch["resultat_net"] = data["resultat_net"]
                    if data["date_cloture_bilan"]:
                        patch["date_cloture_bilan"] = data["date_cloture_bilan"]
                    stats["financial_found"] += 1
                    ca = data.get("chiffre_affaires")
                    rn = data.get("resultat_net")
                    detail = f"CA={ca:,}€" if ca else ""
                    if rn:
                        detail += f" RN={rn:,}€"
                    log(f"  [FIN] {nom:45s} ✓ {detail}")
                else:
                    # Point 2 : pas de enriched_inpi=true sans données ; on garde juste la trace
                    patch = {"inpi_attempted_at": now}

                await patch_lead(session, siren, patch)
                stats["financial_processed"] += 1

            elif task_type == "dirigeant":
                data = await get_dirigeant(session, siren, stats, token_lock, token_holder)

                if data:
                    role = data.pop("dirigeant_role", "")
                    stats["dirigeant_found"] += 1
                    await patch_lead(session, siren, data)
                    log(f"  [DIR] {nom:45s} -> {data['dirigeant_prenom']} {data['dirigeant_nom']} ({role})")
                else:
                    await patch_lead(session, siren, {"dirigeant_nom": ""})

                stats["dirigeant_processed"] += 1

        except Exception as e:
            log(f"  Erreur {task_type} SIREN {siren}: {e}")

        finally:
            queue.task_done()
            stats["processed_total"] += 1

            if stats["processed_total"] % 500 == 0:
                fin_pct = (
                    stats["financial_found"] / stats["financial_processed"] * 100
                    if stats["financial_processed"]
                    else 0
                )
                dir_pct = (
                    stats["dirigeant_found"] / stats["dirigeant_processed"] * 100
                    if stats["dirigeant_processed"]
                    else 0
                )
                log(
                    f"── Progression: {stats['processed_total']} traités "
                    f"(FIN {stats['financial_processed']} / {fin_pct:.1f}%, "
                    f"DIR {stats['dirigeant_processed']} / {dir_pct:.1f}%), "
                    f"API {stats['api_calls']}/{DAILY_QUOTA} ──"
                )

            if stats["api_calls"] >= DAILY_QUOTA and not stop_event.is_set():
                log(f"Quota journalier atteint ({DAILY_QUOTA})")
                stop_event.set()
                for _ in range(MAX_WORKERS):
                    await queue.put(None)


async def main():
    log("=" * 70)
    log("Démarrage enrichissement INPI combiné — financier + dirigeants")
    log(f"Workers: {MAX_WORKERS}, délai: {REQUEST_DELAY}s, quota: {DAILY_QUOTA}")
    log("=" * 70)

    timeout = aiohttp.ClientTimeout(total=60)
    connector = aiohttp.TCPConnector(
        limit=MAX_WORKERS,
        limit_per_host=MAX_WORKERS,
        ttl_dns_cache=300,
        keepalive_timeout=30,
    )
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        token = await inpi_login(session)
        token_holder = {"token": token}
        token_lock = asyncio.Lock()

        log("Chargement des leads sans compter (count Supabase instable)")

        queue = asyncio.Queue()

        fin_fetched = 0
        offset = 0
        while fin_fetched < DAILY_QUOTA:
            batch_size = min(500, DAILY_QUOTA - fin_fetched)
            leads = await fetch_leads(session, {
                "code_naf": "in.(56.10C,56.21Z)",
                "enriched_inpi": "eq.false",
                "inpi_attempted_at": "is.null",
                "order": "score.desc.nullslast",
            }, batch_size, offset)
            if not leads:
                break
            for lead in leads:
                await queue.put(("financial", lead))
            fin_fetched += len(leads)
            offset += len(leads)

        remaining = DAILY_QUOTA - fin_fetched
        dir_fetched = 0
        offset = 0
        while dir_fetched < remaining:
            batch_size = min(500, remaining - dir_fetched)
            leads = await fetch_leads(session, {
                "code_naf": "eq.56.10C",
                "code_postal": "like.75*",
                "enriched_inpi": "eq.true",
                "dirigeant_nom": "is.null",
            }, batch_size, offset)
            if not leads:
                break
            for lead in leads:
                await queue.put(("dirigeant", lead))
            dir_fetched += len(leads)
            offset += len(leads)

        log(f"File prête: {fin_fetched} financiers + {dir_fetched} dirigeants = {queue.qsize()} tâches")

        stats = {
            "api_calls": 0,
            "processed_total": 0,
            "financial_processed": 0,
            "financial_found": 0,
            "dirigeant_processed": 0,
            "dirigeant_found": 0,
        }
        stop_event = asyncio.Event()

        workers = [
            asyncio.create_task(
                worker(f"w{i}", queue, session, stats, token_lock, token_holder, stop_event)
            )
            for i in range(MAX_WORKERS)
        ]

        await queue.join()
        await asyncio.gather(*workers, return_exceptions=True)

    log("=" * 70)
    fin_pct = (
        stats["financial_found"] / stats["financial_processed"] * 100
        if stats["financial_processed"]
        else 0
    )
    dir_pct = (
        stats["dirigeant_found"] / stats["dirigeant_processed"] * 100
        if stats["dirigeant_processed"]
        else 0
    )
    log(f"TERMINÉ: {stats['processed_total']} traités")
    log(f"  Financier: {stats['financial_processed']} traités, {stats['financial_found']} avec CA ({fin_pct:.1f}%)")
    log(f"  Dirigeants: {stats['dirigeant_processed']} traités, {stats['dirigeant_found']} trouvés ({dir_pct:.1f}%)")
    log(f"  Appels API: {stats['api_calls']}/{DAILY_QUOTA}")
    log("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
