"""Contrôle quotidien : une source qui ne produit plus rien est une panne, même si son job est vert.

Vérifie la fraîcheur des données en base et l'état des workflows planifiés, puis envoie UN email
récapitulatif s'il y a un problème (aucun email si tout va bien).

Stdlib uniquement. Usage : python3 scripts/check_data_health.py [--dry-run]
Env : SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, GITHUB_TOKEN, GITHUB_REPOSITORY,
      RESEND_API_KEY, NOTIFICATION_EMAIL_TO.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

NOW = datetime.now(timezone.utc)

# (libellé, chemin REST, colonne date, âge max en jours). Seuils réglés sur le rythme observé
# sur 14 jours, plus une marge pour les retards de GitHub Actions (jusqu'à 12 h).
FRESHNESS_CHECKS = [
    ("Veille (articles)", "news_articles", "created_at", 2),
    ("Appels d'offres (avis)", "tender_notices", "ingested_at", 3),
    ("Appels d'offres (attributions)", "tenders", "ingested_at", 3),
    ("BODACC (procédures et ventes)", "signals?source=eq.bodacc", "ingested_at", 4),
    ("Alim'confiance", "signals?source=eq.alimconfiance", "ingested_at", 21),
    ("Nouveaux leads (Sirene)", "leads", "created_at", 3),
    ("ProFoods (demandes)", "profoods_demandes_clients", "created_at", 6),
    ("ProFoods (matchs)", "profoods_opportunites", "matched_at", 6),
    ("Google Trends (leads)", "leads", "google_trend_last_checked", 8),
]


def supabase_get(path, params):
    base = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    sep = "&" if "?" in path else "?"
    url = f"{base}/rest/v1/{path}{sep}{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"apikey": key, "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def github_get(path):
    req = urllib.request.Request(
        f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/{path}",
        headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def parse_ts(value):
    v = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(v if "T" in v else f"{v}T00:00:00")
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def age_days(dt):
    return (NOW - dt).total_seconds() / 86400


def check_freshness():
    problems = []
    for label, path, column, max_days in FRESHNESS_CHECKS:
        try:
            rows = supabase_get(path, {"select": column, column: "not.is.null", "order": f"{column}.desc", "limit": 1})
        except Exception as exc:
            problems.append(f"{label} : lecture impossible ({exc})")
            continue
        if not rows:
            problems.append(f"{label} : aucune donnée en base")
            continue
        last = parse_ts(rows[0][column])
        if age_days(last) > max_days:
            problems.append(f"{label} : rien de nouveau depuis le {last:%d/%m/%Y} ({age_days(last):.0f} j, seuil {max_days} j)")
    return problems


def check_tender_sources():
    """Chaque source d'appels d'offres : dernier passage récent, en succès, et qui lit quelque chose."""
    since = (NOW - timedelta(days=7)).isoformat()
    rows = supabase_get(
        "tender_source_runs",
        {"select": "source,label,status,started_at,fetched,error", "started_at": f"gte.{since}", "order": "started_at.desc", "limit": 1000},
    )
    by_source = {}
    for r in rows:
        by_source.setdefault(r["source"], []).append(r)
    problems = []
    for source, runs in sorted(by_source.items()):
        last = runs[0]
        name = last.get("label") or source
        if age_days(parse_ts(last["started_at"])) > 3:
            problems.append(f"Source AO « {name} » : dernier passage le {parse_ts(last['started_at']):%d/%m}")
        elif last["status"] == "error":
            problems.append(f"Source AO « {name} » : en erreur ({(last.get('error') or '')[:120]})")
        elif len(runs) >= 3 and all((r.get("fetched") or 0) == 0 for r in runs[:3]):
            problems.append(f"Source AO « {name} » : 0 avis lu sur les 3 derniers passages")
    return problems


def check_workflows():
    """Workflows planifiés (Daily:/Weekly:) : désactivés, en échec, ou sans succès récent."""
    problems = []
    workflows = github_get("actions/workflows?per_page=100")["workflows"]
    for wf in workflows:
        name = wf["name"]
        if not name.startswith(("Daily:", "Weekly:")):
            continue
        if wf["state"] != "active":
            problems.append(f"Workflow « {name} » : désactivé ({wf['state']})")
            continue
        runs = github_get(f"actions/workflows/{wf['id']}/runs?per_page=10&status=completed")["workflow_runs"]
        if not runs:
            problems.append(f"Workflow « {name} » : aucun run terminé")
            continue
        if runs[0]["conclusion"] != "success":
            problems.append(f"Workflow « {name} » : dernier run en {runs[0]['conclusion']} ({runs[0]['html_url']})")
            continue
        max_days = 8 if name.startswith("Weekly:") else 2
        last_ok = parse_ts(runs[0]["created_at"])
        if age_days(last_ok) > max_days:
            problems.append(f"Workflow « {name} » : pas de run réussi depuis le {last_ok:%d/%m}")
    return problems


def send_email(problems):
    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    to_addr = os.environ.get("NOTIFICATION_EMAIL_TO", "").strip()
    if not api_key or not to_addr:
        raise RuntimeError("RESEND_API_KEY ou NOTIFICATION_EMAIL_TO manquant : le rapport ne peut pas partir")
    items = "".join(f"<li style='margin-bottom:6px'>{p}</li>" for p in problems)
    html = (
        "<div style='font-family:Arial,sans-serif;max-width:640px'>"
        f"<h2 style='color:#b91c1c;margin-bottom:4px'>Santé des données : {len(problems)} problème(s)</h2>"
        "<p style='color:#6b7280;margin-top:0'>Une source qui ne produit plus rien est une panne, même si son job est vert.</p>"
        f"<ul>{items}</ul></div>"
    )
    payload = {
        "from": os.environ.get("NOTIFICATION_EMAIL_FROM", "").strip() or "ProKitchens <onboarding@resend.dev>",
        "to": [a.strip() for a in to_addr.split(",") if a.strip()],
        "subject": f"[Santé] {len(problems)} problème(s) — {NOW:%d/%m/%Y}",
        "html": html,
    }
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        print(f"Rapport envoyé (HTTP {resp.status})")


def main():
    dry_run = "--dry-run" in sys.argv
    problems = check_freshness() + check_tender_sources() + check_workflows()
    if not problems:
        print("Tout est à jour.")
        return 0
    print(f"{len(problems)} problème(s) :")
    for p in problems:
        print(f"  - {p}")
    if not dry_run:
        send_email(problems)
    return 0


if __name__ == "__main__":
    sys.exit(main())
