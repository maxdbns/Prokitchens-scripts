"""Ingestion des actualités sectorielles via Google News RSS.

Fetch 14 requêtes FR, tagge par regex, déduplique, upsert dans news_articles,
puis matche les articles récents avec les leads connus.

Usage : python3 scripts/ingest_news.py [--dry-run]
"""
import base64
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from html import unescape

import requests
import urllib3
from googlenewsdecoder import gnewsdecoder

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Charge SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY depuis prokitchens-app/.env
if not os.environ.get("CI"):
    ENV_PATH = os.path.join(os.path.dirname(__file__), "..", "prokitchens-app", ".env")
    if os.path.exists(ENV_PATH):
        for line in open(ENV_PATH):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

SUPABASE_URL = os.environ["NEXT_PUBLIC_SUPABASE_URL"].rstrip("/")
SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
NOTIFICATION_EMAIL_TO = os.environ.get("NOTIFICATION_EMAIL_TO", "")

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"

DIRECT_FEEDS = [
    ("Zepros", "https://www.zepros.fr/rss.xml"),
    ("Food & Sens", "https://foodandsens.com/feed/"),
    ("Hospitality ON", "https://hospitality-on.com/fr/rss.xml"),
    ("Tendances Restauration", "https://tendances-restauration.com/feed/"),
    ("BFM Éco Entreprises", "https://www.bfmtv.com/rss/economie/entreprises/"),
]

QUERIES = [
    "snacking restauration rapide France",
    "dark kitchen cloud kitchen France",
    "ghost kitchen cuisine virtuelle France",
    "franchise restauration ouverture France",
    "livraison repas delivery foodtech France",
    "vente à emporter restauration France",
    "foodtech restauration levée de fonds",
    "restauration rapide ouverture fermeture enseigne",
    "cloud kitchen expansion Europe",
    "cuisine partagée laboratoire cuisine professionnelle",
    "Uber Eats Deliveroo Just Eat restauration France",
    "restauration collective concession catering",
    "réglementation hygiène restaurant DGCCRF",
    "marché restauration hors domicile croissance",
]

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

HOT_KEYWORDS = re.compile(
    r"ouverture|recherche.{0,20}local|recherche.{0,20}emplacement|"
    r"dark.?kitchen|cloud.?kitchen|ghost.?kitchen|cuisine.?partag|"
    r"s.installe|va ouvrir|nouveau restaurant|nouvelle enseigne|"
    r"levée de fonds|expansion|déploiement",
    re.IGNORECASE,
)

TAG_RULES = [
    ("snacking", r"snack|restauration rapide|fast.?food|qsr"),
    ("dark-kitchen", r"dark.?kitchen|cloud.?kitchen|cuisine.?partag|cuisine.?virtuelle|ghost.?kitchen"),
    ("livraison", r"livraison|delivery|uber.?eats|deliveroo|just.?eat|glovo|stuart"),
    ("franchise", r"franchise|enseigne|chaîne|chaine|réseau"),
    ("expansion", r"ouverture|expansion|ouvrir|lancement|inaugur"),
    ("tendance", r"halal|bio|vegan|healthy|végét|sans.?gluten"),
    ("réglementation", r"réglementation|loi|norme|hygiène|contrôle|dgccrf|inspection"),
    ("business", r"chiffre|croissance|marché|résultat|ca\b|bilan|levée|financement|investis"),
    ("alerte", r"fermeture|liquidation|redressement|faillite|difficulté"),
    ("collectif", r"collecti|catering|traiteur|hors.?domicile|concession"),
]


def supabase_headers():
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=ignore-duplicates,return=minimal",
    }


def fetch_rss(query, retries=2):
    """Fetch un flux RSS Google News avec retry."""
    url = f"{GOOGLE_NEWS_RSS}?q={requests.utils.quote(query + ' when:7d')}&hl=fr&gl=FR&ceid=FR:fr&num=20"
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 429:
                wait = 2 ** (attempt + 1)
                print(f"  [rate-limit] {query} — attente {wait}s")
                time.sleep(wait)
                continue
            if not resp.ok:
                print(f"  [http-{resp.status_code}] {query}")
                return []
            return parse_rss(resp.text)
        except requests.RequestException as e:
            print(f"  [error] {query}: {e}")
            if attempt < retries:
                time.sleep(2)
    return []


def parse_rss(xml_text):
    """Parse le XML RSS et retourne une liste d'articles."""
    articles = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    for item in root.iter("item"):
        title = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip()
        pub_date = item.findtext("pubDate", "").strip()
        desc = item.findtext("description", "").strip()
        source_el = item.find("source")
        source = source_el.text.strip() if source_el is not None and source_el.text else ""

        if not title or not link:
            continue

        clean_desc = re.sub(r"<[^>]*>", "", unescape(desc))
        clean_desc = re.sub(r"\s+", " ", clean_desc).strip()

        published_at = None
        if pub_date:
            try:
                from email.utils import parsedate_to_datetime
                published_at = parsedate_to_datetime(pub_date).isoformat()
            except Exception:
                pass

        articles.append({
            "title": title,
            "url": link,
            "source": source,
            "published_at": published_at,
            "description": clean_desc[:500],
        })

    return articles


def guess_tags(title, description):
    text = f"{title} {description}".lower()
    tags = [tag for tag, pattern in TAG_RULES if re.search(pattern, text, re.IGNORECASE)]
    return tags if tags else ["actualité"]


def clean_html(text):
    """Supprime tout HTML résiduel et nettoie le texte."""
    if not text:
        return ""
    text = re.sub(r"<[^>]*>", "", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def build_summary(description):
    if not description:
        return ""
    clean = clean_html(description)
    sentences = re.split(r"(?<=[.!?])\s+", clean)
    return " ".join(sentences[:3])[:300]


def dedupe_by_title(articles):
    seen = set()
    result = []
    for a in articles:
        key = re.sub(r"[^a-zàâéèêëïîôùûüç0-9]", "", a["title"].lower())[:80]
        if key in seen:
            continue
        seen.add(key)
        result.append(a)
    return result


def filter_fresh(articles, max_age_days=7):
    """Ne garde que les articles publiés dans les derniers N jours."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    fresh = []
    skipped = 0
    for a in articles:
        if not a.get("published_at"):
            fresh.append(a)
            continue
        try:
            pub = datetime.fromisoformat(a["published_at"].replace("Z", "+00:00"))
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
            if pub >= cutoff:
                fresh.append(a)
            else:
                skipped += 1
        except (ValueError, TypeError):
            fresh.append(a)
    if skipped:
        print(f"  [fresh] {skipped} articles ignorés (>{max_age_days}j)")
    return fresh


def make_source_id(url):
    return "news:" + base64.urlsafe_b64encode(url.encode()).decode()[:100]


def resolve_google_news_urls(articles):
    """Résout les URLs Google News redirect vers les URLs sources."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def resolve_one(article):
        url = article["url"]
        if "news.google.com/rss/articles/" not in url:
            return article
        try:
            result = gnewsdecoder(url)
            if result.get("status") and result.get("decoded_url"):
                article["url"] = result["decoded_url"]
        except Exception:
            pass
        return article

    resolved = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(resolve_one, a): a for a in articles}
        for future in as_completed(futures):
            a = future.result()
            if "news.google.com" not in a["url"]:
                resolved += 1
    print(f"  [resolve] {resolved}/{len(articles)} URLs résolues vers la source")
    return articles


def upsert_articles(rows, dry_run=False):
    """Upsert par batch de 50."""
    inserted = 0
    for i in range(0, len(rows), 50):
        batch = rows[i:i + 50]
        if dry_run:
            inserted += len(batch)
            continue
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/news_articles?on_conflict=source_id",
            headers=supabase_headers(),
            json=batch,
            timeout=30,
        )
        if resp.ok:
            inserted += len(batch)
        else:
            print(f"  [upsert error] {resp.status_code}: {resp.text[:200]}")
    return inserted


def match_news_to_leads(dry_run=False):
    """Cross-reference articles récents sans lead_id avec la table leads."""
    if dry_run:
        return 0

    # Fetch leads
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/leads?select=id,nom,nom_legal,siren&nom=gte.AAAA",
        headers=supabase_headers(),
        timeout=30,
    )
    if not resp.ok:
        print(f"  [match] leads fetch error: {resp.status_code}")
        return 0
    leads = [l for l in resp.json() if l.get("nom") and len(l["nom"]) >= 4]
    if not leads:
        return 0

    # Fetch articles récents sans lead_id (48h)
    since = (datetime.now(timezone.utc) - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/news_articles"
        f"?select=id,title,summary&lead_id=is.null&created_at=gte.{since}",
        headers=supabase_headers(),
        timeout=30,
    )
    if not resp.ok:
        body = resp.text[:200]
        if "lead_id" in body and "does not exist" in body:
            print("  [match] skipped — column lead_id not yet created (apply migration 20260804)")
        else:
            print(f"  [match] articles fetch error: {resp.status_code} {body}")
        return 0
    articles = resp.json()
    if not articles:
        return 0

    # Build regex patterns
    lead_patterns = []
    for lead in leads:
        names = []
        if lead.get("nom") and len(lead["nom"]) >= 4:
            names.append(lead["nom"])
        if lead.get("nom_legal") and len(lead["nom_legal"]) >= 4:
            names.append(lead["nom_legal"])
        if names:
            escaped = [re.escape(n) for n in names]
            lead_patterns.append((lead, re.compile(r"\b(" + "|".join(escaped) + r")\b", re.IGNORECASE)))

    matched = 0
    for article in articles:
        text = f"{article['title']} {article.get('summary', '')}"
        for lead, pattern in lead_patterns:
            if pattern.search(text):
                r = requests.patch(
                    f"{SUPABASE_URL}/rest/v1/news_articles?id=eq.{article['id']}",
                    headers=supabase_headers(),
                    json={"lead_id": lead["id"]},
                    timeout=10,
                )
                if r.ok:
                    matched += 1
                break

    if matched:
        print(f"  [match] {matched} article(s) lié(s) à des leads")
    return matched


def send_hot_alerts(new_articles, dry_run=False):
    """Envoie un email pour les articles qui matchent des mots-clés chauds."""
    if not RESEND_API_KEY or not NOTIFICATION_EMAIL_TO:
        return 0

    hot = [a for a in new_articles if HOT_KEYWORDS.search(f"{a['title']} {a.get('summary', '')}")]
    if not hot:
        return 0

    tag_colors = {
        "snacking": "#e67e22", "dark-kitchen": "#8e44ad", "livraison": "#3498db",
        "franchise": "#27ae60", "expansion": "#2ecc71", "tendance": "#1abc9c",
        "réglementation": "#e74c3c", "business": "#f39c12", "alerte": "#e74c3c",
        "collectif": "#1abc9c", "actualité": "#95a5a6",
    }

    rows = ""
    for a in hot[:15]:
        pills = "".join(
            f'<span style="display:inline-block;padding:2px 8px;border-radius:10px;'
            f'background:{tag_colors.get(t, "#95a5a6")};color:#fff;font-size:11px;'
            f'margin-right:4px">{t}</span>'
            for t in (a.get("tags") or [])
        )
        rows += f"""
        <tr style="border-bottom:1px solid #eee">
          <td style="padding:12px 0">
            <a href="{a['url']}" style="color:#333;text-decoration:none;font-weight:bold">{a['title']}</a><br/>
            <span style="color:#888;font-size:13px">{a.get('source', 'Google News')}</span>
            {f'<br/>{pills}' if pills else ''}
          </td>
        </tr>"""

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto">
      <h2 style="color:#c8ad86;margin-bottom:4px">ProKitchens — Alertes chaudes</h2>
      <p style="color:#999;font-size:13px;margin-top:0">{len(hot)} article(s) avec des signaux business</p>
      <table style="width:100%;border-collapse:collapse">{rows}</table>
      <p style="margin-top:20px;color:#999;font-size:12px">ProKitchens Sales Hub</p>
    </div>"""

    if dry_run:
        print(f"  [hot] {len(hot)} articles chauds (dry-run, email non envoyé)")
        return len(hot)

    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": "ProKitchens <onboarding@resend.dev>",
                "to": [e.strip() for e in NOTIFICATION_EMAIL_TO.split(",")],
                "subject": f"[ProKitchens] {len(hot)} alerte(s) veille sectorielle",
                "html": html,
            },
            timeout=15,
        )
        if resp.ok:
            print(f"  [hot] {len(hot)} alertes envoyées par email")
        else:
            print(f"  [hot] email error: {resp.status_code}")
    except Exception as e:
        print(f"  [hot] email error: {e}")

    return len(hot)


def cleanup_old_articles(retention_days=14):
    """Purge les articles dont published_at est plus vieux que retention_days."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    resp = requests.delete(
        f"{SUPABASE_URL}/rest/v1/news_articles?published_at=lt.{cutoff}",
        headers=supabase_headers(),
        timeout=30,
    )
    if resp.ok:
        print(f"  [cleanup] purgé les articles >{retention_days}j")
    else:
        print(f"  [cleanup] error: {resp.status_code}")


def main():
    dry_run = "--dry-run" in sys.argv

    print(f"[news] Démarrage ingestion ({len(QUERIES)} requêtes)...")
    if not dry_run:
        cleanup_old_articles(retention_days=14)
    all_articles = []

    # Batch par groupes de 5 pour éviter le rate limiting
    for i in range(0, len(QUERIES), 5):
        batch = QUERIES[i:i + 5]
        for q in batch:
            articles = fetch_rss(q)
            print(f"  [{len(articles):3d}] {q}")
            all_articles.extend(articles)
        if i + 5 < len(QUERIES):
            time.sleep(1)

    # Flux RSS directs (sources métier)
    print(f"[news] Fetch {len(DIRECT_FEEDS)} flux RSS directs...")
    for name, feed_url in DIRECT_FEEDS:
        try:
            resp = requests.get(feed_url, headers=HEADERS, timeout=15, verify=False)
            if resp.ok:
                articles = parse_rss(resp.text)
                for a in articles:
                    if not a["source"]:
                        a["source"] = name
                print(f"  [{len(articles):3d}] {name} (direct)")
                all_articles.extend(articles)
            else:
                print(f"  [fail] {name}: HTTP {resp.status_code}")
        except Exception as e:
            print(f"  [fail] {name}: {e}")

    print(f"[news] {len(all_articles)} articles bruts récupérés")

    all_articles = filter_fresh(all_articles, max_age_days=7)
    print(f"[news] {len(all_articles)} articles frais (≤7j)")

    unique = dedupe_by_title(all_articles)
    print(f"[news] {len(unique)} articles après dédup")

    # Résolution des URLs Google News vers les sources
    unique = resolve_google_news_urls(unique)

    rows = []
    seen_sid = set()
    for a in unique:
        sid = make_source_id(a["url"])
        if sid in seen_sid:
            continue
        seen_sid.add(sid)
        rows.append({
            "source": a["source"] or "Google News",
            "source_id": sid,
            "title": a["title"][:500],
            "summary": build_summary(a["description"]),
            "url": a["url"],
            "published_at": a["published_at"],
            "tags": guess_tags(a["title"], a["description"]),
            "raw_content": clean_html(a["description"])[:2000] or None,
        })

    print(f"[news] {len(rows)} articles à upserter")

    # Identifier les nouveaux articles (pas encore en base)
    if not dry_run and rows:
        sids = [r["source_id"] for r in rows]
        existing = set()
        for i in range(0, len(sids), 50):
            batch_sids = sids[i:i + 50]
            in_filter = ",".join(f'"{s}"' for s in batch_sids)
            resp = requests.get(
                f"{SUPABASE_URL}/rest/v1/news_articles?select=source_id&source_id=in.({in_filter})",
                headers=supabase_headers(),
                timeout=15,
            )
            if resp.ok:
                existing.update(r["source_id"] for r in resp.json())
        new_rows = [r for r in rows if r["source_id"] not in existing]
    else:
        new_rows = rows

    inserted = upsert_articles(rows, dry_run)
    print(f"[news] {inserted} articles upsertés ({len(new_rows)} nouveaux)")

    # Alertes hot keywords sur les nouveaux articles
    hot_count = send_hot_alerts(new_rows, dry_run)

    matched = match_news_to_leads(dry_run)
    sources = sorted(set(a["source"] or "Google News" for a in unique))

    print(f"[news] Terminé — {inserted} upserted, {hot_count} alertes, {matched} matched, {len(sources)} sources")
    if dry_run:
        print("[news] DRY RUN — aucune écriture")


if __name__ == "__main__":
    main()
