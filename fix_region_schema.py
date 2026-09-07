#!/usr/bin/env python3
"""
Fix missing 'region' column in Supabase leads table
This fixes the schema cache error that's been blocking all data syncs since Aug 13
"""

import os
import sys
from pathlib import Path

# Load Supabase credentials
sys.path.insert(0, str(Path(__file__).parent / "prokitchens-app"))
from prokitchens_env import load_env

load_env()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY")

if not SUPABASE_URL or not SUPABASE_API_KEY:
    print("❌ ERREUR: SUPABASE_URL et SUPABASE_API_KEY requis")
    print("   Assurez-vous que .env.local est configuré correctement")
    sys.exit(1)

import requests

def run_sql(sql: str) -> dict:
    """Execute SQL in Supabase"""
    headers = {
        "Authorization": f"Bearer {SUPABASE_API_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }

    response = requests.post(
        f"{SUPABASE_URL}/rest/v1/rpc/exec_sql",
        headers=headers,
        json={"sql": sql}
    )

    if response.status_code not in (200, 204):
        print(f"❌ Erreur SQL: {response.status_code}")
        print(response.text)
        return {"error": response.text}

    return {"success": True}

def main():
    print("🔧 Fixing ProKitchens Supabase schema...\n")

    # Step 1: Add region column
    print("[1/3] Adding 'region' column to leads table...")
    migration_file = Path(__file__).parent / "prokitchens-app" / "migrations" / "20260907_add_region_column.sql"

    if not migration_file.exists():
        print(f"❌ Migration file not found: {migration_file}")
        sys.exit(1)

    migration_sql = migration_file.read_text()

    # Split and execute statements
    statements = [s.strip() for s in migration_sql.split(";") if s.strip() and not s.strip().startswith("--")]

    for i, stmt in enumerate(statements, 1):
        print(f"\n  [{i}] Executing: {stmt[:60]}...")
        result = run_sql(stmt)
        if "error" in result:
            print(f"  ❌ Failed: {result['error']}")
            sys.exit(1)
        else:
            print(f"  ✅ Success")

    print("\n✅ Schema migration completed!")
    print("\n📋 Next steps:")
    print("  1. Re-run the workflows on GitHub Actions")
    print("  2. Check app sync status (should now work)")
    print("  3. Monitor logs for any remaining issues")

if __name__ == "__main__":
    main()
