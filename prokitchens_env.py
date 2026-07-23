import os
from pathlib import Path

ROOT = Path("/zpool/one/maxime.debaugnies")
APP_DIR = ROOT / "prokitchens-app"


def _load_env_file(path: Path) -> dict:
    env = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            env[key] = value
    return env


def load_env() -> None:
    """Load prokitchens-app/.env and .env.local, then set script aliases."""
    for fname in (".env", ".env.local"):
        for key, value in _load_env_file(APP_DIR / fname).items():
            if key not in os.environ:
                os.environ[key] = value

    # Compatibility aliases used by root Python scripts
    if not os.environ.get("SUPABASE_URL") and os.environ.get("NEXT_PUBLIC_SUPABASE_URL"):
        os.environ["SUPABASE_URL"] = os.environ["NEXT_PUBLIC_SUPABASE_URL"]
    if not os.environ.get("SUPABASE_API_KEY") and os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
        os.environ["SUPABASE_API_KEY"] = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
