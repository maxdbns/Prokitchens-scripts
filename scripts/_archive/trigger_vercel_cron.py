#!/usr/bin/env python3
"""
Déclenche le cron Vercel /api/cron/daily après l'enrichissement nocturne.
Lu par lead_scheduler.py.
"""
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

ROOT_DIR = Path(os.environ.get("PROKITCHENS_ROOT", "/zpool/one/maxime.debaugnies"))
APP_DIR = ROOT_DIR / "prokitchens-app"


def load_env_file(path: Path) -> dict:
    env = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def main():
    env: dict = dict(os.environ)
    if not os.environ.get("CI"):
        for env_file in [".env", ".env.local", ".env.production.local"]:
            env.update(load_env_file(APP_DIR / env_file))

    cron_secret = env.get("CRON_SECRET")
    site_url = env.get("NEXT_PUBLIC_SITE_URL") or env.get("VERCEL_URL")
    if not site_url:
        print("NEXT_PUBLIC_SITE_URL ou VERCEL_URL manquant")
        return 1
    if not cron_secret:
        print("CRON_SECRET manquant")
        return 1

    site_url = site_url.rstrip("/")
    if not site_url.startswith("http://") and not site_url.startswith("https://"):
        site_url = "https://" + site_url
    url = f"{site_url}/api/cron/daily"

    req = urllib.request.Request(
        url,
        method="GET",
        headers={"Authorization": f"Bearer {cron_secret}"},
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            print(f"HTTP {resp.status} {resp.reason}")
            print(body[:500])
            return 0 if resp.status == 200 else 1
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code} {e.reason}")
        print(body[:500])
        return 1
    except Exception as e:
        print(f"Erreur: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
