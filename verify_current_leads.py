import requests
import time
from collections import Counter

SUPABASE_URL = "https://hxjryfaakdpwfgseirik.supabase.co"
SUPABASE_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imh4anJ5ZmFha2Rwd2Znc2VpcmlrIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MjkwMzgwMCwiZXhwIjoyMDk4NDc5ODAwfQ.gGba1EWAucnG7kaI2E__-lSWj1yAQjyEp2LpltFiKKw"
PAGE_SIZE = 1000


def supabase_headers():
    return {
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}",
        "Content-Type": "application/json",
    }


# Count via HEAD with count exact
resp = requests.head(
    f"{SUPABASE_URL}/rest/v1/leads",
    headers={**supabase_headers(), "Prefer": "count=exact"},
    params={"select": "siren"},
)
print("HEAD status:", resp.status_code)
print("Content-Range:", resp.headers.get("Content-Range"))
content_range = resp.headers.get("Content-Range", "")
total_leads = 0
if "/" in content_range:
    total_leads = int(content_range.split("/")[-1])
print(f"Total leads (count exact): {total_leads}")

# Paginate all sirens
all_sirens = []
offset = 0
while True:
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/leads",
        headers={**supabase_headers(), "Range": f"{offset}-{offset + PAGE_SIZE - 1}"},
        params={"select": "siren", "order": "siren"},
    )
    if resp.status_code == 416:
        break
    if resp.status_code != 200:
        print(f"Error {resp.status_code}: {resp.text[:200]}")
        break
    rows = resp.json()
    if not rows:
        break
    all_sirens.extend([r["siren"] for r in rows if r.get("siren")])
    if len(rows) < PAGE_SIZE:
        break
    offset += PAGE_SIZE
    if offset % 10000 == 0:
        print(f"  Fetched {offset} rows...")

print(f"Total rows fetched: {len(all_sirens)}")
print(f"Distinct SIREN: {len(set(all_sirens))}")
print(f"SIREN with multiple leads: {sum(1 for c in Counter(all_sirens).values() if c > 1)}")
