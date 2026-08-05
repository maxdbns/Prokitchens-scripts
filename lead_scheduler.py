#!/usr/bin/env python3
"""
Scheduler gratuit pour le pipeline de leads ProKitchens.

Comme ni crontab ni systemd ne sont disponibles dans cet environnement,
ce script tourne en daemon via nohup et déclenche les scripts d'enrichissement
aux horaires programmés.

Tâches :
- 02:30  daily_sirene_delta.py          delta Sirene (nouveaux / maj / fermetures)
- 03:30  dimanche  run-insee-sync.sh    sync INSEE multi-sites (nouvelles enseignes / expansions, manuel/hebdo)
- 04:00  backfill-etablissements.py     réparation des établissements manquants
- 04:30  fix-lead-names.sh              correction automatique des noms de leads
- 05:00  enrich_contact.py              enrichissement email/téléphone depuis le web
- 06:00  inpi_enrich_dirigeants.py   dirigeants INPI (quotidien, ~3h30, timeout 5h)
- 07:00  dimanche  cleanup_closed_sirets.py    nettoyage SIREN sans établissement actif
- 08:00  dimanche  cleanup_closed_leads.py     nettoyage SIREN radiés/cessés
- 09:00  trigger_vercel_cron.py         déclenche les notifications Vercel après enrichissement

Lancement :
    cd /zpool/one/maxime.debaugnies
    nohup python3 lead_scheduler.py > lead_scheduler.log 2>&1 &
    echo $! > lead_scheduler.pid

Arrêt :
    kill $(cat lead_scheduler.pid)
"""

import os
import sys
import subprocess
import time
import fcntl
import datetime
import logging
import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import List, Tuple, Optional

# ─── Config ───
ROOT_DIR = Path("/zpool/one/maxime.debaugnies")
APP_DIR = ROOT_DIR / "prokitchens-app"
ENV_FILE = APP_DIR / ".env"

LOG_FILE = ROOT_DIR / "logs" / "lead_scheduler.log"
PID_FILE = ROOT_DIR / "lead_scheduler.pid"
LOCK_FILE = ROOT_DIR / "lead_scheduler.lock"

SCHEDULE = [
    # (heure, minute, jour_semaine ou None, nom, [commande], cwd, description)
    # jour_semaine : 0=lundi ... 6=dimanche, None = tous les jours
    (2, 30, None, "daily_sirene_delta",
     [sys.executable, str(ROOT_DIR / "daily_sirene_delta.py")], ROOT_DIR,
     "Delta Sirene quotidien (nouveaux / maj / fermetures)"),
    (3, 30, 6, "run-insee-sync",
     ["/bin/bash", str(ROOT_DIR / "run-insee-sync.sh")], ROOT_DIR,
     "Sync INSEE multi-sites (nouvelles enseignes / expansions, hebdomadaire)"),
    (4, 0, None, "backfill-etablissements",
     [sys.executable, str(APP_DIR / "scripts" / "backfill-etablissements.py")], APP_DIR,
     "Réparation des établissements manquants"),
    (4, 30, None, "fix-lead-names",
     ["/bin/bash", str(ROOT_DIR / "run-fix-lead-names.sh")], ROOT_DIR,
     "Correction automatique des noms de leads depuis les établissements"),
    (5, 0, None, "enrich_contact",
     [sys.executable, str(ROOT_DIR / "enrich_contact.py")], ROOT_DIR,
     "Enrichissement email/téléphone depuis le web"),
    (7, 0, None, "profoods_enrich_enseignes",
     [sys.executable, str(ROOT_DIR / "scripts" / "enrich_enseignes.py")], ROOT_DIR,
     "Noms d'enseigne ProFoods (après la sync Vercel UnEmplacement de 5h30)"),
    (7, 30, None, "profoods_enrich_commentaires",
     [sys.executable, str(ROOT_DIR / "scripts" / "enrich_commentaires.py")], ROOT_DIR,
     "Commentaires des recherches ProFoods (critères + précisions zones)"),
    (6, 0, None, "inpi_enrich_dirigeants",
     [sys.executable, str(ROOT_DIR / "inpi_enrich_dirigeants.py")], ROOT_DIR,
     "Enrichissement dirigeants INPI"),
    (7, 0, 6, "cleanup_closed_sirets",
     [sys.executable, str(ROOT_DIR / "cleanup_closed_sirets.py")], ROOT_DIR,
     "Nettoyage SIREN sans établissement actif"),
    (8, 0, 6, "cleanup_closed_leads",
     [sys.executable, str(ROOT_DIR / "cleanup_closed_leads.py")], ROOT_DIR,
     "Nettoyage SIREN radiés/cessés"),
    (9, 0, None, "vercel_notifications",
     [sys.executable, str(ROOT_DIR / "trigger_vercel_cron.py")], ROOT_DIR,
     "Déclenche les notifications Vercel après l'enrichissement"),
    (10, 30, None, "revalidate_google",
     [sys.executable, str(ROOT_DIR / "trigger_revalidate_google.py")], ROOT_DIR,
     "Re-validation Google / site web pour les leads existants faiblement appariés"),
]

CHECK_INTERVAL_SECONDS = 60


# ─── Logging ───
# En mode daemon (nohup), stdout est redirigé vers le fichier de log. On évite
# alors d'ajouter un StreamHandler pour ne pas écrire chaque ligne deux fois.
handlers = [logging.FileHandler(LOG_FILE)]
if sys.stdout.isatty():
    handlers.append(logging.StreamHandler(sys.stdout))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=handlers,
)
log = logging.getLogger("lead_scheduler")


# ─── Env loading ───
def load_env_file(path: Path) -> dict:
    """Charge un fichier .env simple (KEY=VALUE, sans substitution)."""
    env = {}
    if not path.exists():
        log.warning(f"Fichier env non trouvé : {path}")
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def build_env() -> dict:
    """Construit l'environnement pour les sous-process."""
    env = os.environ.copy()

    # 1. Charger les variables du projet Next.js
    app_env = load_env_file(ENV_FILE)
    env.update(app_env)

    # 2. Les scripts Python racine utilisent SUPABASE_API_KEY ; il faut la clé service-role
    service_role = env.get("SUPABASE_SERVICE_ROLE_KEY")
    if service_role:
        env["SUPABASE_API_KEY"] = service_role
    else:
        log.warning("SUPABASE_SERVICE_ROLE_KEY non trouvée ; les scripts racine risquent d'échouer en écriture")

    # 3. Les scripts racine utilisent SUPABASE_URL (et pas NEXT_PUBLIC_SUPABASE_URL)
    if "NEXT_PUBLIC_SUPABASE_URL" in env and "SUPABASE_URL" not in env:
        env["SUPABASE_URL"] = env["NEXT_PUBLIC_SUPABASE_URL"]

    return env


# ─── Lock / single instance ───
class SingleInstance:
    def __init__(self, lock_path: Path):
        self.lock_path = lock_path
        self.lock_file = None

    def __enter__(self):
        self.lock_file = open(self.lock_path, "w")
        try:
            fcntl.lockf(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log.error("Un autre scheduler est déjà en cours. Arrêt.")
            sys.exit(1)
        self.lock_file.write(str(os.getpid()))
        self.lock_file.flush()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.lock_file:
            fcntl.lockf(self.lock_file, fcntl.LOCK_UN)
            self.lock_file.close()
        try:
            self.lock_path.unlink()
        except FileNotFoundError:
            pass


# ─── Task runner ───
def run_task(name: str, command: List[str], cwd: Path, env: dict) -> Tuple[int, str]:
    """Exécute une commande et retourne (code, log_path)."""
    log.info(f"▶ Démarrage {name}: {' '.join(command)}")
    started = datetime.datetime.now()

    task_log = ROOT_DIR / "logs" / f"lead_scheduler_{name}_{started.strftime('%Y%m%d_%H%M%S')}.log"

    try:
        with open(task_log, "w") as out:
            proc = subprocess.Popen(
                command,
                cwd=cwd,
                env=env,
                stdout=out,
                stderr=subprocess.STDOUT,
            )
            if name == "inpi_enrich_dirigeants":
                task_timeout = 5 * 3600
            elif name == "profoods_enrich_commentaires":
                task_timeout = 3 * 3600
            else:
                task_timeout = 3600
            try:
                rc = proc.wait(timeout=task_timeout)
            except subprocess.TimeoutExpired:
                log.warning(f"  {name} dépasse {task_timeout // 3600}h, on tue le process")
                proc.kill()
                rc = -1
    except Exception as e:
        log.error(f"  {name} erreur d'exécution : {e}")
        task_log.write_text(str(e))
        return -1, str(task_log)

    elapsed = datetime.datetime.now() - started
    if rc == 0:
        log.info(f"✓ {name} terminé en {elapsed} (log: {task_log})")
    else:
        log.error(f"✗ {name} échoué (code {rc}) en {elapsed} (log: {task_log})")
    return rc, str(task_log)


# ─── Scheduling ───
def should_run_now(hour: int, minute: int, weekday: Optional[int]) -> bool:
    now = datetime.datetime.now()
    if now.hour != hour or now.minute != minute:
        return False
    if weekday is not None and now.weekday() != weekday:
        return False
    return True


def last_run_date(name: str) -> Optional[datetime.date]:
    """Renvoie la date du dernier run réussi, ou None."""
    marker = ROOT_DIR / f".lead_scheduler_last_run_{name}"
    if not marker.exists():
        return None
    try:
        text = marker.read_text().strip()
        return datetime.datetime.strptime(text.split("_")[0], "%Y-%m-%d").date()
    except Exception:
        return None


def already_ran_today(name: str, hour: int, minute: int) -> bool:
    """Vérifie si la tâche a déjà été lancée aujourd'hui à l'heure donnée."""
    marker = ROOT_DIR / f".lead_scheduler_last_run_{name}"
    if not marker.exists():
        return False
    try:
        last_run = marker.read_text().strip()
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        return last_run == f"{today}_{hour:02d}:{minute:02d}"
    except Exception:
        return False


def mark_ran(name: str, hour: int, minute: int):
    marker = ROOT_DIR / f".lead_scheduler_last_run_{name}"
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    marker.write_text(f"{today}_{hour:02d}:{minute:02d}")


def send_health_alert(overdue_tasks: list, env: dict):
    """Envoie une alerte email via l'endpoint Vercel /api/health/scheduler."""
    site_url = env.get("NEXT_PUBLIC_SITE_URL") or env.get("VERCEL_URL", "")
    cron_secret = env.get("CRON_SECRET", "")
    if not site_url or not cron_secret:
        log.warning("Alerte santé : NEXT_PUBLIC_SITE_URL ou CRON_SECRET manquant, pas d'email envoyé")
        return

    site_url = site_url.rstrip("/")
    if not site_url.startswith("http"):
        site_url = "https://" + site_url
    url = f"{site_url}/api/health/scheduler"

    payload = json.dumps({"overdue": overdue_tasks}).encode()
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={
            "Authorization": f"Bearer {cron_secret}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode()
            log.info(f"Alerte santé envoyée : {body}")
    except Exception as e:
        log.error(f"Alerte santé échec : {e}")


def catch_up(env: dict):
    """Rattrapage au démarrage : exécute les tâches qui n'ont pas tourné depuis >24h."""
    today = datetime.datetime.now().date()
    overdue = []

    for hour, minute, weekday, name, command, cwd, desc in SCHEDULE:
        if weekday is not None and today.weekday() != weekday:
            continue
        last = last_run_date(name)
        if last is None or (today - last).days >= 1:
            overdue.append((hour, minute, weekday, name, command, cwd, desc))

    if not overdue:
        log.info("Rattrapage : toutes les tâches sont à jour ✓")
        return

    log.info(f"Rattrapage : {len(overdue)} tâche(s) en retard, exécution immédiate")
    alert_tasks = []
    for hour, minute, weekday, name, command, cwd, desc in overdue:
        last = last_run_date(name)
        retard = (today - last).days if last else "jamais"
        log.info(f"  ⏰ {name} — dernier run : {last or 'jamais'} (retard : {retard} jour(s))")
        alert_tasks.append({
            "name": name,
            "last_run": str(last) if last else None,
            "retard_jours": retard,
            "status": "never" if last is None else "overdue",
        })

    send_health_alert(alert_tasks, env)

    for hour, minute, weekday, name, command, cwd, desc in overdue:
        mark_ran(name, hour, minute)
        run_task(name, command, cwd, env)


# ─── Main loop ───
def main():
    log.info("=" * 60)
    log.info("Lead Scheduler — démarrage")
    log.info(f"PID : {os.getpid()}")
    log.info("=" * 60)

    env = build_env()
    if not env.get("SUPABASE_SERVICE_ROLE_KEY"):
        log.error("SUPABASE_SERVICE_ROLE_KEY manquante. Arrêt.")
        sys.exit(1)

    # Rattrapage des tâches manquées (crash nocturne, redémarrage tardif, etc.)
    catch_up(env)

    # Optionnel : lancer immédiatement le backfill si le fichier de flag existe
    if (ROOT_DIR / ".lead_scheduler_run_now").exists():
        log.info("Flag run_now détecté, exécution immédiate du backfill")
        run_task("backfill-etablissements",
                 [sys.executable, str(APP_DIR / "scripts" / "backfill-etablissements.py")],
                 APP_DIR, env)
        try:
            (ROOT_DIR / ".lead_scheduler_run_now").unlink()
        except FileNotFoundError:
            pass

    last_minute = -1
    while True:
        now = datetime.datetime.now()
        current_minute = now.hour * 60 + now.minute

        # N'évalue qu'une fois par minute
        if current_minute != last_minute:
            last_minute = current_minute

            for hour, minute, weekday, name, command, cwd, desc in SCHEDULE:
                if should_run_now(hour, minute, weekday) and not already_ran_today(name, hour, minute):
                    mark_ran(name, hour, minute)
                    run_task(name, command, cwd, env)

        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    with SingleInstance(LOCK_FILE):
        try:
            main()
        except KeyboardInterrupt:
            log.info("Arrêt demandé par l'utilisateur")
        except Exception as e:
            log.exception(f"ERREUR FATALE : {e}")
            sys.exit(1)
