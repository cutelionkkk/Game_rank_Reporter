"""Crawlers for Google Play and iOS App Store game rankings"""

import json
import os
import subprocess
import time
import traceback
from datetime import datetime, timezone

try:
    from scrapling.fetchers import Fetcher as ScraplingFetcher
    _USE_SCRAPLING = True
except ImportError:
    import requests
    _USE_SCRAPLING = False

from config import COUNTRY, TOP_N, load_settings
from database import insert_rankings, log_crawl, init_db
from genres import GENRES, get_genre, format_chart_label

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
GP_SCRAPER = os.path.join(SCRIPT_DIR, "gp_scraper.js")
NODE_PATH = subprocess.check_output(["npm", "root", "-g"], text=True,
                                     stderr=subprocess.DEVNULL).strip()


# ============================================================
# Google Play Crawler (via Node.js google-play-scraper)
# ============================================================

def crawl_gp_chart(chart_type, genre_id="all", country=None, top_n=None):
    """Crawl a Google Play game chart using Node.js scraper
    
    Args:
        chart_type: free | paid | grossing
        genre_id: genre key from genres.py (e.g. "casual", "puzzle", "all")
        country: country code override
        top_n: top N override
    """
    country = country or COUNTRY
    top_n = top_n or TOP_N
    
    genre = get_genre(genre_id)
    if not genre:
        print(f"  ❌ Unknown genre: {genre_id}")
        return []
    
    gp_category = genre.get("gp_category")
    if not gp_category:
        print(f"  ⚠️ Genre '{genre_id}' not available on Google Play")
        return []

    env = os.environ.copy()
    env["NODE_PATH"] = NODE_PATH

    try:
        result = subprocess.run(
            ["node", GP_SCRAPER, chart_type, country, str(top_n), gp_category],
            capture_output=True, text=True, timeout=120, env=env,
        )

        if result.returncode != 0:
            print(f"  ❌ Node scraper error: {result.stderr.strip()}")
            return []

        # stdout may contain proxychains noise; find the JSON array
        stdout = result.stdout
        json_start = stdout.find('[')
        if json_start < 0:
            print(f"  ❌ No JSON in output")
            return []

        raw = json.loads(stdout[json_start:])
        results = []
        for item in raw:
            results.append({
                'rank': item['rank'],
                'app_id': item['app_id'],
                'app_name': item['app_name'],
                'developer': item.get('developer'),
                'category': item.get('category'),
                'rating': item.get('rating'),
                'rating_count': item.get('rating_count'),
                'price': item.get('price'),
                'icon_url': item.get('icon_url'),
                'extra_json': json.dumps(item.get('extra', {}), ensure_ascii=False),
            })
        return results

    except subprocess.TimeoutExpired:
        print(f"  ❌ Node scraper timeout (120s)")
        return []
    except Exception as e:
        print(f"  ❌ GP crawl error: {e}")
        traceback.print_exc()
        return []


# ============================================================
# iOS App Store Crawler (RSS feeds)
# ============================================================

IOS_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
}

# RSS feed URL builders
def _ios_old_rss_url(chart_type, genre_id, country, top_n):
    """Build old iTunes RSS URL with genre support"""
    feed_map = {
        'free': 'topfreeapplications',
        'paid': 'toppaidapplications',
        'grossing': 'topgrossingapplications',
    }
    feed_name = feed_map.get(chart_type)
    if not feed_name:
        return None
    
    genre = get_genre(genre_id)
    if not genre:
        return None
    
    ios_genre = genre.get("ios_genre_id")
    if not ios_genre:
        return None
    
    return f"https://itunes.apple.com/{country}/rss/{feed_name}/limit={top_n}/genre={ios_genre}/json"


def _ios_v2_rss_url(chart_type, country, top_n):
    """Build Apple RSS v2 URL (no genre filtering)"""
    v2_map = {
        'free': f"https://rss.applemarketingtools.com/api/v2/{country}/apps/top-free/{top_n}/apps.json",
        'paid': f"https://rss.applemarketingtools.com/api/v2/{country}/apps/top-paid/{top_n}/apps.json",
    }
    return v2_map.get(chart_type)


def _parse_ios_v2(data, top_n=100):
    """Parse Apple RSS v2 feed"""
    results = []
    for i, app in enumerate(data.get('feed', {}).get('results', [])[:top_n], 1):
        genres = app.get('genres', [])
        category = genres[0].get('name', '') if genres else ''
        results.append({
            'rank': i,
            'app_id': app.get('id', ''),
            'app_name': app.get('name', ''),
            'developer': app.get('artistName', ''),
            'category': category,
            'rating': None,
            'rating_count': None,
            'price': None,
            'icon_url': app.get('artworkUrl100', ''),
            'extra_json': json.dumps({
                'url': app.get('url', ''),
                'releaseDate': app.get('releaseDate', ''),
                'kind': app.get('kind', ''),
            }, ensure_ascii=False),
        })
    return results


def _parse_ios_old(data, top_n=100):
    """Parse old iTunes RSS feed"""
    results = []
    for i, entry in enumerate(data.get('feed', {}).get('entry', [])[:top_n], 1):
        cat = entry.get('category', {})
        category = cat.get('attributes', {}).get('label', '') if isinstance(cat, dict) else ''

        id_data = entry.get('id', {})
        app_id = id_data.get('attributes', {}).get('im:id', '') if isinstance(id_data, dict) else ''

        name_data = entry.get('im:name', {})
        app_name = name_data.get('label', '') if isinstance(name_data, dict) else ''

        artist = entry.get('im:artist', {})
        developer = artist.get('label', '') if isinstance(artist, dict) else ''

        results.append({
            'rank': i,
            'app_id': app_id,
            'app_name': app_name,
            'developer': developer,
            'category': category,
            'rating': None,
            'rating_count': None,
            'price': None,
            'icon_url': '',
            'extra_json': json.dumps({
                'summary': ((entry.get('summary', {}) or {}).get('label', '') or '')[:200],
                'releaseDate': (entry.get('im:releaseDate', {}) or {}).get('label', ''),
            }, ensure_ascii=False),
        })
    return results


def crawl_ios_chart(chart_type, genre_id="all", country=None, top_n=None):
    """Crawl an iOS App Store game chart
    
    For genre_id="all" + free/paid: use RSS v2 (better data, but no genre filter)
    For specific genres OR grossing: use old iTunes RSS (supports genre=XXXX)
    """
    country = country or COUNTRY
    top_n = top_n or TOP_N
    
    genre = get_genre(genre_id)
    if not genre:
        print(f"  ❌ Unknown genre: {genre_id}")
        return []
    
    if genre.get("ios_genre_id") is None:
        print(f"  ⚠️ Genre '{genre_id}' not available on iOS")
        return []

    # Strategy:
    # - "all" + free/paid → try v2 first (better data), fallback to old RSS
    # - "all" + grossing → old RSS (v2 doesn't have grossing)
    # - specific genre → always old RSS (v2 doesn't support genre filter)
    
    use_v2 = (genre_id == "all" and chart_type in ['free', 'paid'])
    
    if use_v2:
        v2_url = _ios_v2_rss_url(chart_type, country, top_n)
        if v2_url:
            try:
                if _USE_SCRAPLING:
                    page = ScraplingFetcher.get(v2_url, headers=IOS_HEADERS, timeout=30)
                    ok = page.status == 200
                    get_json = page.json
                else:
                    resp = requests.get(v2_url, headers=IOS_HEADERS, timeout=30)
                    ok = resp.status_code == 200
                    get_json = resp.json
                if ok:
                    results = _parse_ios_v2(get_json(), top_n)
                    if results:
                        print(f"  📍 {len(results)} apps via RSS v2")
                        return results
            except Exception as e:
                print(f"  ⚠️ iOS RSS v2 failed: {e}")

    # Old iTunes RSS (with genre)
    old_url = _ios_old_rss_url(chart_type, genre_id, country, top_n)
    if old_url:
        try:
            if _USE_SCRAPLING:
                page = ScraplingFetcher.get(old_url, headers=IOS_HEADERS, timeout=30)
                if page.status != 200:
                    raise Exception(f"HTTP {page.status}")
                resp_json = page.json
            else:
                resp = requests.get(old_url, headers=IOS_HEADERS, timeout=30)
                resp.raise_for_status()
                resp_json = resp.json
            results = _parse_ios_old(resp_json(), top_n)
            if results:
                source = f"iTunes RSS (genre={genre.get('ios_genre_id')})"
                print(f"  📍 {len(results)} apps via {source}")
                return results
        except Exception as e:
            print(f"  ⚠️ iOS old RSS failed: {e}")

    return []


# ============================================================
# Main Crawl Orchestrator
# ============================================================

def _get_chart_list():
    """Get the list of charts to crawl from settings"""
    settings = load_settings()
    chart_list = settings.get("chart_list")
    
    if chart_list:
        # New format: explicit chart list with genres
        return chart_list
    
    # Legacy format: platforms × charts (all genres)
    platforms = settings.get("platforms", ["ios", "gp"])
    charts = settings.get("charts", ["free", "paid", "grossing"])
    result = []
    for p in platforms:
        for c in charts:
            result.append({"platform": p, "chart_type": c, "genre": "all"})
    return result


def run_full_crawl():
    """Run a full crawl of all configured charts"""
    init_db()
    crawl_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    chart_list = _get_chart_list()
    
    print(f"\n🕐 Crawl started at {crawl_time}")
    print(f"📋 {len(chart_list)} charts to crawl")
    print("=" * 50)

    total = 0
    errors = []

    for chart_conf in chart_list:
        platform = chart_conf["platform"]
        chart_type = chart_conf["chart_type"]
        genre_id = chart_conf.get("genre", "all")
        
        label = format_chart_label(platform, chart_type, genre_id)
        platform_emoji = "🍎" if platform == "ios" else "📱"
        print(f"\n{platform_emoji} {label}")
        
        # Build a unique key for DB storage: platform + chart_type + genre
        db_chart_type = chart_type if genre_id == "all" else f"{chart_type}:{genre_id}"
        
        t0 = time.time()
        try:
            if platform == "ios":
                items = crawl_ios_chart(chart_type, genre_id)
            elif platform == "gp":
                items = crawl_gp_chart(chart_type, genre_id)
            else:
                print(f"  ❌ Unknown platform: {platform}")
                continue
            
            dt = time.time() - t0
            if items:
                n = insert_rankings(crawl_time, platform, db_chart_type, items)
                log_crawl(crawl_time, platform, db_chart_type, n, 'ok', duration=dt)
                print(f"  ✅ {n} games ({dt:.1f}s)")
                total += n
            else:
                log_crawl(crawl_time, platform, db_chart_type, 0, 'error', 'No results', duration=dt)
                errors.append(f"{label}: no results")
                print(f"  ⚠️ No results")
        except Exception as e:
            dt = time.time() - t0
            log_crawl(crawl_time, platform, db_chart_type, 0, 'error', str(e), duration=dt)
            errors.append(f"{label}: {e}")
            print(f"  ❌ {e}")

    print(f"\n{'=' * 50}")
    print(f"📊 Done: {total} total entries across {len(chart_list)} charts")
    if errors:
        print(f"⚠️ {len(errors)} errors:")
        for e in errors:
            print(f"   - {e}")

    return crawl_time, total, errors


if __name__ == "__main__":
    run_full_crawl()
