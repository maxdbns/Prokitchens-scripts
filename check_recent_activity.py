"""
Vérifie l'activité récente sur la base Supabase (cron, leads, notifications).
"""

import os
import requests
from datetime import datetime, timedelta, timezone

import prokitchens_env
prokitchens_env.load_env()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY", "")


def supabase_headers():
    return {
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}",
        "Content-Type": "application/json",
    }


def query_table(table, params):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    resp = requests.get(url, headers=supabase_headers(), params=params)
    if resp.status_code != 200:
        print(f"  ⚠ {table}: HTTP {resp.status_code} {resp.text[:200]}")
        return []
    return resp.json()


def main():
    print("=== Vérification de l'activité récente sur Supabase ===\n")

    # 1. Derniers leads créés / mis à jour
    print("1. Derniers leads (created_at / updated_at)")
    for col in ["created_at", "updated_at"]:
        rows = query_table(
            "leads",
            {"select": col, "order": f"{col}.desc", "limit": 5},
        )
        if rows:
            print(f"   {col}: {rows[0].get(col)}")

    # 2. Nombre de leads créés / mis à jour cette semaine
    print("\n2. Leads créés / mis à jour les 7 derniers jours")
    one_week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    for col in ["created_at", "updated_at"]:
        resp = requests.head(
            f"{SUPABASE_URL}/rest/v1/leads",
            headers={**supabase_headers(), "Prefer": "count=exact"},
            params={col: f"gte.{one_week_ago}", "select": "id"},
        )
        if resp.status_code == 200:
            content_range = resp.headers.get("Content-Range", "")
            count = content_range.split("/")[-1] if "/" in content_range else "?"
            print(f"   {col} >= 7 jours : {count} leads")
        else:
            print(f"   ⚠ {col}: HTTP {resp.status_code}")

    # 3. Dernières notifications
    print("\n3. Dernières notifications (notifications)")
    rows = query_table(
        "notifications",
        {"select": "type,title,created_at", "order": "created_at.desc", "limit": 10},
    )
    if rows:
        for r in rows:
            print(f"   {r.get('created_at')} | {r.get('type')} | {r.get('title')}")
    else:
        print("   Aucune notification trouvée")

    # 4. Nombre de notifications cette semaine
    print("\n4. Notifications des 7 derniers jours")
    resp = requests.head(
        f"{SUPABASE_URL}/rest/v1/notifications",
        headers={**supabase_headers(), "Prefer": "count=exact"},
        params={"created_at": f"gte.{one_week_ago}", "select": "id"},
    )
    if resp.status_code == 200:
        content_range = resp.headers.get("Content-Range", "")
        count = content_range.split("/")[-1] if "/" in content_range else "?"
        print(f"   Nombre : {count}")
    else:
        print(f"   ⚠ HTTP {resp.status_code}")

    # 5. Nouvelles ouvertures détectées (leads avec updated_at récent et nb_etablissements >= 2)
    print("\n5. Leads récemment mis à jour avec >= 2 établissements")
    rows = query_table(
        "leads",
        {
            "select": "id,nom,nb_etablissements,derniere_ouverture,updated_at",
            "updated_at": f"gte.{one_week_ago}",
            "nb_etablissements": "gte.2",
            "order": "updated_at.desc",
            "limit": 10,
        },
    )
    if rows:
        for r in rows:
            print(f"   {r.get('updated_at')} | {r.get('nom')} | nb={r.get('nb_etablissements')} | ouverture={r.get('derniere_ouverture')}")
    else:
        print("   Aucun")


if __name__ == "__main__":
    main()
