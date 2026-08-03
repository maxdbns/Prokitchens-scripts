#!/usr/bin/env python3
"""
Processeur de requetes AI via Claude Code CLI.

Poll Supabase ai_requests (status=pending), appelle claude -p, ecrit la reponse.

Lancement :  bash start_ai_processor.sh
Arret :      bash stop_ai_processor.sh
"""

import os
import sys
import subprocess
import time
import fcntl
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests as http_requests

import prokitchens_env
prokitchens_env.load_env()

ROOT_DIR = Path("/zpool/one/maxime.debaugnies")
LOCK_FILE = ROOT_DIR / "ai_request_processor.lock"
LOG_FILE = ROOT_DIR / "logs" / "ai_request_processor.log"

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY", "")

POLL_INTERVAL = 15
CLAUDE_TIMEOUT = 120
CLAUDE_BIN = "/usr/local/bin/claude"
STALE_THRESHOLD = 300  # 5 min


def log(msg: str):
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def headers(prefer="return=representation"):
    return {
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def reset_stale_processing():
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=STALE_THRESHOLD)).isoformat()
    url = (
        f"{SUPABASE_URL}/rest/v1/ai_requests"
        f"?status=eq.processing&started_at=lt.{cutoff}"
    )
    try:
        resp = http_requests.patch(
            url,
            json={"status": "pending", "started_at": None},
            headers=headers(),
            timeout=10,
        )
        if resp.ok and resp.text.strip() not in ("", "[]"):
            rows = resp.json()
            if rows:
                log(f"Reset {len(rows)} requete(s) bloquee(s) en processing")
    except Exception as e:
        log(f"Erreur reset stale: {e}")


def fetch_pending():
    url = (
        f"{SUPABASE_URL}/rest/v1/ai_requests"
        f"?status=eq.pending&order=created_at.asc&limit=1"
    )
    try:
        resp = http_requests.get(url, headers=headers(), timeout=10)
        if not resp.ok:
            return None
        rows = resp.json()
        if not rows:
            return None
    except Exception as e:
        log(f"Erreur fetch pending: {e}")
        return None

    row = rows[0]
    claim_url = (
        f"{SUPABASE_URL}/rest/v1/ai_requests"
        f"?id=eq.{row['id']}&status=eq.pending"
    )
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        claim_resp = http_requests.patch(
            claim_url,
            json={"status": "processing", "started_at": now_iso},
            headers=headers(),
            timeout=10,
        )
        if not claim_resp.ok:
            return None
        claimed = claim_resp.json()
        if not claimed:
            return None
        return claimed[0]
    except Exception as e:
        log(f"Erreur claim: {e}")
        return None


def update_request(request_id: str, status: str, response=None, error=None):
    url = f"{SUPABASE_URL}/rest/v1/ai_requests?id=eq.{request_id}"
    payload = {
        "status": status,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    if response is not None:
        payload["response"] = response
    if error is not None:
        payload["error"] = error
    try:
        http_requests.patch(url, json=payload, headers=headers("return=minimal"), timeout=10)
    except Exception as e:
        log(f"Erreur update {request_id}: {e}")


def process_request(row: dict):
    request_id = row["id"]
    req_type = row.get("type", "?")
    prompt = row["prompt"]
    log(f"Traitement {request_id} (type={req_type}, {len(prompt)} chars)")

    try:
        result = subprocess.run(
            [CLAUDE_BIN, "-p", prompt],
            capture_output=True,
            text=True,
            timeout=CLAUDE_TIMEOUT,
            cwd=str(ROOT_DIR),
        )

        if result.returncode == 0 and result.stdout.strip():
            update_request(request_id, "completed", response=result.stdout.strip())
            log(f"OK {request_id} ({len(result.stdout.strip())} chars)")
        else:
            error_msg = result.stderr.strip() or f"claude exit code {result.returncode}"
            update_request(request_id, "error", error=error_msg)
            log(f"Erreur {request_id}: {error_msg[:200]}")

    except subprocess.TimeoutExpired:
        update_request(request_id, "error", error=f"Timeout apres {CLAUDE_TIMEOUT}s")
        log(f"Timeout {request_id}")
    except Exception as e:
        update_request(request_id, "error", error=str(e))
        log(f"Exception {request_id}: {e}")


class SingleInstance:
    def __init__(self, lock_path: Path):
        self.lock_path = lock_path
        self.lock_file = None

    def __enter__(self):
        self.lock_file = open(self.lock_path, "w")
        try:
            fcntl.lockf(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log("Un autre ai_request_processor est deja en cours. Arret.")
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


def main():
    log("=" * 50)
    log("AI Request Processor — demarrage")
    log(f"PID: {os.getpid()}")
    log(f"Poll: {POLL_INTERVAL}s | Claude timeout: {CLAUDE_TIMEOUT}s")
    log("=" * 50)

    if not SUPABASE_URL or not SUPABASE_API_KEY:
        log("ERREUR: SUPABASE_URL ou SUPABASE_API_KEY manquante")
        sys.exit(1)

    reset_stale_processing()

    while True:
        try:
            row = fetch_pending()
            if row:
                process_request(row)
                continue
        except Exception as e:
            log(f"Erreur boucle principale: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    with SingleInstance(LOCK_FILE):
        try:
            main()
        except KeyboardInterrupt:
            log("Arret demande (Ctrl+C)")
        except Exception as e:
            log(f"ERREUR FATALE: {e}")
            sys.exit(1)
