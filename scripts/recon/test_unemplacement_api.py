"""Test direct de l'API UnEmplacement : login Firebase + fetch_prospections."""
import json
import os

import requests

FIREBASE_API_KEY = "AIzaSyBrV4UUSZyoEmUGeWYOT8JmVNCNps0-tBk"
EMAIL = os.environ["UNEMPLACEMENT_EMAIL"]
PASSWORD = os.environ["UNEMPLACEMENT_PASSWORD"]


def get_id_token():
    r = requests.post(
        f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}",
        json={"returnSecureToken": True, "email": EMAIL, "password": PASSWORD},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["idToken"]


def fetch_prospections(token, page=0, prospection_type=1, state="Île-de-France"):
    r = requests.post(
        "https://api.app.unemplacement.com/member_api/fetch_prospections",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "state": state,
            "locations": [],
            "filters": {
                "prospectionType": prospection_type,
                "commercialMinSurface": "",
                "commercialMaxSurface": "",
                "commercialActivityTypes": [],
                "commercialStatusesV2": [],
                "typeFilter": [],
                "query": "",
                "commercialPlaceTypes": [],
                "search_criteria": None,
                "research_locations": [],
                "match_all_locations": True,
            },
            "page": page,
            "hits_per_page": 20,
            "reload_all": False,
            "cached_list_new": None,
            "version": 2,
        },
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


if __name__ == "__main__":
    token = get_id_token()
    print("[OK] Token Firebase obtenu")

    for ptype in (1, 2):
        data = fetch_prospections(token, page=0, prospection_type=ptype)
        print(f"\n=== prospectionType={ptype} — structure: {type(data).__name__}")
        if isinstance(data, list):
            for i, seg in enumerate(data):
                if isinstance(seg, list):
                    print(f"  segment {i}: {len(seg)} items")
                else:
                    print(f"  segment {i}: {json.dumps(seg, ensure_ascii=False)[:300]}")
            items = data[0] if data and isinstance(data[0], list) else []
            if items:
                it = items[0]
                print(f"  exemple: ref={it.get('reference_id')} user_status_v2={it.get('user_status_v2')} "
                      f"type={it.get('type')} activity_type={it.get('activity_type')} "
                      f"surface={it.get('total_surface')} locations={[l.get('nom') for l in it.get('locations', [])]}")
