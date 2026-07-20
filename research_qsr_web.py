"""
Recherche web de chaînes de restauration rapide en croissance en France.
Utilise Bing (pas d'API key requis).
"""

import requests
import re
import time
import csv
from urllib.parse import quote_plus

QUERIES = [
    "chaînes restauration rapide croissance France 2024 2025",
    "top 50 enseignes restauration rapide France LSA 2024",
    "nouvelles enseignes fast casual France expansion",
    "dark kitchen France expansion 2024 2025",
    "chaines de burgers tacos poke bowls France croissance",
    "franchises restauration rapide en croissance France",
]

OUTPUT_CSV = "researched_chains_raw.csv"


def search_bing(query):
    url = f"https://www.bing.com/search?q={quote_plus(query)}&setmkt=fr-FR&setlang=fr"
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "fr-FR,fr;q=0.9",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code != 200:
            print(f"Erreur HTTP {resp.status_code} pour {query}")
            return []
        return resp.text
    except Exception as e:
        print(f"Erreur requete {query}: {e}")
        return []


def extract_results(html):
    results = []
    # Bing : h2 > a
    links = re.findall(r'<li class="b_algo"[^>]*>.*?<h2><a href="([^"]+)"[^>]*>(.*?)</a></h2>.*?</li>', html, re.S)
    for url, title in links:
        title = re.sub(r'<[^>]+>', '', title).strip()
        if title and url and url.startswith("http"):
            results.append({"title": title, "url": url})
    return results


def main():
    all_results = []
    for query in QUERIES:
        print(f"Recherche : {query}")
        html = search_bing(query)
        if html:
            results = extract_results(html)
            for r in results:
                r["query"] = query
            all_results.extend(results)
            print(f"  {len(results)} resultats")
        time.sleep(2)

    with open(OUTPUT_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["query", "title", "url"])
        writer.writeheader()
        writer.writerows(all_results)

    print(f"\nTotal resultats : {len(all_results)}")
    print(f"Fichier : {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
