"""Envoie une alerte email via Resend quand un job GitHub Actions échoue.

Stdlib uniquement (pas de pip install requis) pour fonctionner même si
l'échec a eu lieu avant l'installation des dépendances.

Env requis : RESEND_API_KEY, NOTIFICATION_EMAIL_TO.
Env optionnel (fourni par GitHub Actions) : GITHUB_WORKFLOW, GITHUB_JOB,
GITHUB_REPOSITORY, GITHUB_SERVER_URL, GITHUB_RUN_ID.
"""
import json
import os
import sys
import urllib.request


def main() -> int:
    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    to_addr = os.environ.get("NOTIFICATION_EMAIL_TO", "").strip()
    if not api_key or not to_addr:
        print("RESEND_API_KEY ou NOTIFICATION_EMAIL_TO manquant, alerte non envoyée")
        return 0

    workflow = os.environ.get("GITHUB_WORKFLOW", "workflow inconnu")
    job = os.environ.get("GITHUB_JOB", "job inconnu")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    run_url = f"{server}/{repo}/actions/runs/{run_id}" if repo and run_id else ""

    subject = f"❌ Échec : {workflow} ({job})"
    html = (
        f"<p>Le job <b>{job}</b> du workflow <b>{workflow}</b> a échoué.</p>"
        f"<p><a href=\"{run_url}\">Voir le run</a></p>"
    )

    payload = {
        "from": "ProKitchens <onboarding@resend.dev>",
        "to": [to_addr],
        "subject": subject,
        "html": html,
    }
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"Alerte envoyée à {to_addr} (HTTP {resp.status})")
    except Exception as exc:
        print(f"Échec envoi alerte : {exc}")
    return 0  # ne jamais faire échouer le job à cause de l'alerte


if __name__ == "__main__":
    sys.exit(main())
