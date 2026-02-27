"""Crawlers for Google Play and iOS App Store game rankings"""

import json
import time
import re
import traceback
from datetime import datetime, timezone

import requests
from google_play_scraper import app as gp_app_detail

from config import COUNTRY, TOP_N
from database import insert_rankings, log_crawl, init_db


# ============================================================
# Google Play Crawler
# ============================================================

GP_CHART_URLS = {
    'free': 'https://play.google.com/store/games?gl={country}&hl=en',
    'paid': 'https://play.google.com/store/apps/collection/topselling_paid_game?gl={country}&hl=en',
    'grossing': 'https://play.google.com/store/apps/collection/topgrossing_game?gl={country}&hl=en',
}

GP_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
}


def _extract_gp_app_ids(html):
    """Extract app IDs from Google Play HTML"""
    apps = re.findall(r'details\?id=([a-zA-Z0-9._]+)', html)
    seen = list(dict.fromkeys(apps))  # deduplicate, preserve order
    return seen


def _get_gp_details(app_ids, max_items=100):
    """Fetch details for a list of GP app IDs"""
    results = []
    for i, pkg in enumerate(app_ids[:max_items], 1):
        try:
            info = gp_app_detail(pkg, lang='en', country=COUNTRY)
            results.append({
                'rank': i,
                'app_id': pkg,
                'app_name': info.get('title', pkg),
                'developer': info.get('developer', ''),
                'category': info.get('genre', ''),
                'rating': info.get('score'),
                'rating_count': info.get('ratings'),
                'price': info.get('price', 0),
                'icon_url': info.get('icon', ''),
                'extra_json': json.dumps({
                    'installs': info.get('installs', ''),
                    'free': info.get('free', True),
                    'containsAds': info.get('containsAds', False),
                    'contentRating': info.get('contentRating', ''),
                    'genreId': info.get('genreId', ''),
                    'url': info.get('url', ''),
                    'released': info.get('released', ''),
                    'lastUpdated': str(info.get('updated', '')),
                    'realInstalls': info.get('realInstalls', 0),
                    'minInstalls': info.get('minInstalls', 0),
                }, ensure_ascii=False),
            })
            # Rate limiting
            if i % 10 == 0:
                time.sleep(0.5)
                print(f"    ... {i}/{min(len(app_ids), max_items)} apps fetched")
        except Exception as e:
            results.append({
                'rank': i,
                'app_id': pkg,
                'app_name': pkg,
                'developer': None,
                'category': None,
                'rating': None,
                'rating_count': None,
                'price': None,
                'icon_url': None,
                'extra_json': json.dumps({'error': str(e)}),
            })
    return results


def crawl_gp_chart(chart_type):
    """Crawl a Google Play game chart"""
    # Primary: try specific chart URL
    urls_to_try = []
    
    if chart_type == 'free':
        urls_to_try = [
            f'https://play.google.com/store/games?gl={COUNTRY}&hl=en',
            f'https://play.google.com/store/apps/collection/topselling_free_game?gl={COUNTRY}&hl=en',
        ]
    elif chart_type == 'paid':
        urls_to_try = [
            f'https://play.google.com/store/apps/collection/topselling_paid_game?gl={COUNTRY}&hl=en',
            f'https://play.google.com/store/apps/top?gl={COUNTRY}&hl=en',
        ]
    elif chart_type == 'grossing':
        urls_to_try = [
            f'https://play.google.com/store/apps/collection/topgrossing_game?gl={COUNTRY}&hl=en',
            f'https://play.google.com/store/apps/top?gl={COUNTRY}&hl=en',
        ]

    all_app_ids = []

    for url in urls_to_try:
        try:
            resp = requests.get(url, headers=GP_HEADERS, timeout=30)
            if resp.status_code == 200:
                ids = _extract_gp_app_ids(resp.text)
                if ids:
                    all_app_ids = ids
                    print(f"  📍 Got {len(ids)} apps from {url.split('?')[0].split('/')[-1] or 'games'}")
                    break
        except Exception as e:
            continue

    if not all_app_ids:
        print(f"  ⚠️ No GP apps found for {chart_type}")
        return []

    # Filter to games only (by checking genreId) and get details
    print(f"  📥 Fetching details for {min(len(all_app_ids), TOP_N)} apps...")
    results = _get_gp_details(all_app_ids, TOP_N)

    # Filter: only keep actual games (genreId starts with GAME_)
    game_results = []
    non_game_count = 0
    for r in results:
        try:
            extra = json.loads(r.get('extra_json', '{}') or '{}')
            genre_id = extra.get('genreId', '')
            if genre_id.startswith('GAME') or not genre_id:
                game_results.append(r)
            else:
                non_game_count += 1
        except:
            game_results.append(r)

    if non_game_count > 0:
        print(f"  🎮 Filtered out {non_game_count} non-game apps")
        # Re-rank
        for i, r in enumerate(game_results, 1):
            r['rank'] = i

    return game_results


# ============================================================
# iOS App Store Crawler
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


def _parse_ios_v2_feed(data, top_n=100):
    """Parse iOS RSS v2 feed"""
    results = []
    feed = data.get('feed', {})
    apps = feed.get('results', [])

    for i, app in enumerate(apps[:top_n], 1):
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


def _parse_ios_old_feed(data, top_n=100):
    """Parse old iTunes RSS feed"""
    results = []
    entries = data.get('feed', {}).get('entry', [])

    for i, entry in enumerate(entries[:top_n], 1):
        category = ''
        cat_data = entry.get('category', {})
        if isinstance(cat_data, dict):
            category = cat_data.get('attributes', {}).get('label', '')

        app_id = ''
        id_data = entry.get('id', {})
        if isinstance(id_data, dict):
            app_id = id_data.get('attributes', {}).get('im:id', '')

        app_name = ''
        name_data = entry.get('im:name', {})
        if isinstance(name_data, dict):
            app_name = name_data.get('label', '')

        developer = ''
        artist_data = entry.get('im:artist', {})
        if isinstance(artist_data, dict):
            developer = artist_data.get('label', '')

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
                'summary': (entry.get('summary', {}).get('label', '') or '')[:200],
                'releaseDate': entry.get('im:releaseDate', {}).get('label', ''),
            }, ensure_ascii=False),
        })
    return results


def crawl_ios_chart(chart_type):
    """Crawl an iOS App Store game chart"""
    results = []

    # Try v2 RSS first (free & paid only, no grossing)
    v2_url = IOS_FEEDS_V2.get(chart_type)
    if v2_url:
        try:
            resp = requests.get(v2_url, headers=IOS_HEADERS, timeout=30)
            if resp.status_code == 200:
                results = _parse_ios_v2_feed(resp.json(), TOP_N)
                if results:
                    print(f"  📍 Got {len(results)} apps from RSS v2")
                    return results
        except Exception as e:
            print(f"  ⚠️ iOS RSS v2 failed for {chart_type}: {e}")

    # Fallback: old iTunes RSS (genre=6014 = Games)
    old_url = IOS_FEEDS_OLD.get(chart_type)
    if old_url:
        try:
            resp = requests.get(old_url, headers=IOS_HEADERS, timeout=30)
            resp.raise_for_status()
            results = _parse_ios_old_feed(resp.json(), TOP_N)
            if results:
                print(f"  📍 Got {len(results)} apps from old iTunes RSS")
                return results
        except Exception as e:
            print(f"  ⚠️ iOS old RSS also failed for {chart_type}: {e}")

    # Last resort: try grossing via different genre path
    if chart_type == 'grossing':
        try:
            url = f"https://rss.applemarketingtools.com/api/v2/{COUNTRY}/apps/top-grossing/{TOP_N}/apps.json"
            resp = requests.get(url, headers=IOS_HEADERS, timeout=30)
            if resp.status_code == 200:
                results = _parse_ios_v2_feed(resp.json(), TOP_N)
                if results:
                    return results
        except:
            pass

    return results


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

    # --- iOS (faster, RSS-based) ---
    for chart_type in ['free', 'paid', 'grossing']:
        print(f"\n🍎 iOS App Store — {chart_type.upper()}")
        t0 = time.time()
        try:
            items = crawl_ios_chart(chart_type)
            duration = time.time() - t0
            if items:
                count = insert_rankings(crawl_time, 'ios', chart_type, items)
                log_crawl(crawl_time, 'ios', chart_type, count, 'ok', duration=duration)
                print(f"  ✅ {count} games saved ({duration:.1f}s)")
                total += count
            else:
                log_crawl(crawl_time, 'ios', chart_type, 0, 'error', 'No results', duration=duration)
                errors.append(f"iOS {chart_type}: no results")
                print(f"  ⚠️ No results")
        except Exception as e:
            duration = time.time() - t0
            log_crawl(crawl_time, 'ios', chart_type, 0, 'error', str(e), duration=duration)
            errors.append(f"iOS {chart_type}: {e}")
            print(f"  ❌ Error: {e}")
            traceback.print_exc()

    # --- Google Play (slower, needs scraping + API) ---
    for chart_type in ['free', 'paid', 'grossing']:
        print(f"\n📱 Google Play — {chart_type.upper()}")
        t0 = time.time()
        try:
            items = crawl_gp_chart(chart_type)
            duration = time.time() - t0
            if items:
                count = insert_rankings(crawl_time, 'gp', chart_type, items)
                log_crawl(crawl_time, 'gp', chart_type, count, 'ok', duration=duration)
                print(f"  ✅ {count} games saved ({duration:.1f}s)")
                total += count
            else:
                log_crawl(crawl_time, 'gp', chart_type, 0, 'error', 'No results', duration=duration)
                errors.append(f"GP {chart_type}: no results")
                print(f"  ⚠️ No results")
        except Exception as e:
            duration = time.time() - t0
            log_crawl(crawl_time, 'gp', chart_type, 0, 'error', str(e), duration=duration)
            errors.append(f"GP {chart_type}: {e}")
            print(f"  ❌ Error: {e}")
            traceback.print_exc()

    print(f"\n{'=' * 50}")
    print(f"📊 Crawl complete: {total} total entries")
    if errors:
        print(f"⚠️ Errors: {len(errors)}")
        for err in errors:
            print(f"   - {err}")

    return crawl_time, total, errors


if __name__ == "__main__":
    run_full_crawl()
