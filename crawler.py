"""Crawlers for Google Play and iOS App Store game rankings"""

import json
import os
import subprocess
import time
import traceback
from datetime import datetime, timezone

import requests

from config import COUNTRY, TOP_N
from database import insert_rankings, log_crawl, init_db

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
GP_SCRAPER = os.path.join(SCRIPT_DIR, "gp_scraper.js")
NODE_PATH = subprocess.check_output(["npm", "root", "-g"], text=True,
                                     stderr=subprocess.DEVNULL).strip()


# ============================================================
# Google Play Crawler (via Node.js google-play-scraper)
# ============================================================

def crawl_gp_chart(chart_type):
    """Crawl a Google Play game chart using Node.js scraper"""
    env = os.environ.copy()
    env["NODE_PATH"] = NODE_PATH

    try:
        result = subprocess.run(
            ["node", GP_SCRAPER, chart_type, COUNTRY, str(TOP_N)],
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

IOS_FEEDS_V2 = {
    'free': f"https://rss.applemarketingtools.com/api/v2/{COUNTRY}/apps/top-free/{TOP_N}/apps.json",
    'paid': f"https://rss.applemarketingtools.com/api/v2/{COUNTRY}/apps/top-paid/{TOP_N}/apps.json",
}

IOS_FEEDS_OLD = {
    'free': f"https://itunes.apple.com/{COUNTRY}/rss/topfreeapplications/limit={TOP_N}/genre=6014/json",
    'paid': f"https://itunes.apple.com/{COUNTRY}/rss/toppaidapplications/limit={TOP_N}/genre=6014/json",
    'grossing': f"https://itunes.apple.com/{COUNTRY}/rss/topgrossingapplications/limit={TOP_N}/genre=6014/json",
}

IOS_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
}


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
    """Parse old iTunes RSS feed (genre=6014 = Games)"""
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


def crawl_ios_chart(chart_type):
    """Crawl an iOS App Store game chart"""
    # Try v2 RSS first (free & paid)
    v2_url = IOS_FEEDS_V2.get(chart_type)
    if v2_url:
        try:
            resp = requests.get(v2_url, headers=IOS_HEADERS, timeout=30)
            if resp.status_code == 200:
                results = _parse_ios_v2(resp.json(), TOP_N)
                if results:
                    print(f"  📍 {len(results)} apps via RSS v2")
                    return results
        except Exception as e:
            print(f"  ⚠️ iOS RSS v2 failed: {e}")

    # Fallback: old iTunes RSS (Games genre=6014)
    old_url = IOS_FEEDS_OLD.get(chart_type)
    if old_url:
        try:
            resp = requests.get(old_url, headers=IOS_HEADERS, timeout=30)
            resp.raise_for_status()
            results = _parse_ios_old(resp.json(), TOP_N)
            if results:
                print(f"  📍 {len(results)} apps via iTunes RSS")
                return results
        except Exception as e:
            print(f"  ⚠️ iOS old RSS failed: {e}")

    return []


# ============================================================
# Main Crawl Orchestrator
# ============================================================

def run_full_crawl():
    """Run a full crawl of all charts"""
    init_db()
    crawl_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"\n🕐 Crawl started at {crawl_time}")
    print("=" * 50)

    total = 0
    errors = []

    # --- iOS (fast, RSS-based) ---
    for chart_type in ['free', 'paid', 'grossing']:
        print(f"\n🍎 iOS — {chart_type.upper()}")
        t0 = time.time()
        try:
            items = crawl_ios_chart(chart_type)
            dt = time.time() - t0
            if items:
                n = insert_rankings(crawl_time, 'ios', chart_type, items)
                log_crawl(crawl_time, 'ios', chart_type, n, 'ok', duration=dt)
                print(f"  ✅ {n} games ({dt:.1f}s)")
                total += n
            else:
                log_crawl(crawl_time, 'ios', chart_type, 0, 'error', 'No results', duration=dt)
                errors.append(f"iOS {chart_type}: no results")
                print(f"  ⚠️ No results")
        except Exception as e:
            dt = time.time() - t0
            log_crawl(crawl_time, 'ios', chart_type, 0, 'error', str(e), duration=dt)
            errors.append(f"iOS {chart_type}: {e}")
            print(f"  ❌ {e}")

    # --- Google Play (Node.js scraper) ---
    for chart_type in ['free', 'paid', 'grossing']:
        print(f"\n📱 GP — {chart_type.upper()}")
        t0 = time.time()
        try:
            items = crawl_gp_chart(chart_type)
            dt = time.time() - t0
            if items:
                n = insert_rankings(crawl_time, 'gp', chart_type, items)
                log_crawl(crawl_time, 'gp', chart_type, n, 'ok', duration=dt)
                print(f"  ✅ {n} games ({dt:.1f}s)")
                total += n
            else:
                log_crawl(crawl_time, 'gp', chart_type, 0, 'error', 'No results', duration=dt)
                errors.append(f"GP {chart_type}: no results")
                print(f"  ⚠️ No results")
        except Exception as e:
            dt = time.time() - t0
            log_crawl(crawl_time, 'gp', chart_type, 0, 'error', str(e), duration=dt)
            errors.append(f"GP {chart_type}: {e}")
            print(f"  ❌ {e}")

    print(f"\n{'=' * 50}")
    print(f"📊 Done: {total} total entries")
    if errors:
        print(f"⚠️ {len(errors)} errors:")
        for e in errors:
            print(f"   - {e}")

    return crawl_time, total, errors


if __name__ == "__main__":
    run_full_crawl()
