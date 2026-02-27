"""Analyzer for game ranking changes and trends"""

import json
from datetime import datetime, timedelta, timezone
from collections import defaultdict

from database import (
    get_rankings_at, get_previous_crawl_time, get_latest_crawl_time,
    get_app_rank_history, get_category_stats, get_all_crawl_times, get_db
)
from config import RANK_SURGE_THRESHOLD, NEW_ENTRY_DAYS, REPORT_MAX_ITEMS


def analyze_chart_changes(platform, chart_type, current_time, previous_time):
    """Compare two crawls and find changes"""
    current = get_rankings_at(current_time, platform, chart_type)
    previous = get_rankings_at(previous_time, platform, chart_type) if previous_time else []

    prev_map = {r['app_id']: r for r in previous}
    curr_map = {r['app_id']: r for r in current}

    changes = {
        'new_entries': [],      # 新上榜
        'surges': [],           # 排名飙升
        'drops': [],            # 排名暴跌
        'exits': [],            # 跌出榜单
        'top_movers_up': [],    # 所有上升
        'top_movers_down': [],  # 所有下降
        'stable_top': [],       # 稳定在顶部
    }

    for app in current:
        app_id = app['app_id']
        if app_id not in prev_map:
            # New entry
            extra = {}
            try:
                extra = json.loads(app.get('extra_json', '{}') or '{}')
            except:
                pass
            release_date = extra.get('releaseDate', '')
            is_new_game = False
            if release_date:
                try:
                    rd = datetime.fromisoformat(release_date.replace('Z', '+00:00'))
                    is_new_game = (datetime.now(timezone.utc) - rd).days <= NEW_ENTRY_DAYS
                except:
                    pass

            changes['new_entries'].append({
                **app,
                'is_new_game': is_new_game,
            })
        else:
            prev_rank = prev_map[app_id]['rank']
            curr_rank = app['rank']
            diff = prev_rank - curr_rank  # positive = moved up

            if diff >= RANK_SURGE_THRESHOLD:
                changes['surges'].append({**app, 'prev_rank': prev_rank, 'rank_change': diff})
            elif diff <= -RANK_SURGE_THRESHOLD:
                changes['drops'].append({**app, 'prev_rank': prev_rank, 'rank_change': diff})

            if diff > 0:
                changes['top_movers_up'].append({**app, 'prev_rank': prev_rank, 'rank_change': diff})
            elif diff < 0:
                changes['top_movers_down'].append({**app, 'prev_rank': prev_rank, 'rank_change': diff})
            else:
                if curr_rank <= 10:
                    changes['stable_top'].append(app)

    # Exits (was in previous, not in current)
    for app_id, app in prev_map.items():
        if app_id not in curr_map:
            changes['exits'].append(app)

    # Sort
    changes['surges'].sort(key=lambda x: x['rank_change'], reverse=True)
    changes['drops'].sort(key=lambda x: x['rank_change'])
    changes['top_movers_up'].sort(key=lambda x: x['rank_change'], reverse=True)
    changes['top_movers_down'].sort(key=lambda x: x['rank_change'])
    changes['new_entries'].sort(key=lambda x: x['rank'])

    return changes


def analyze_category_trends(platform, chart_type, days=7):
    """Analyze category distribution trends over time"""
    crawl_times = get_all_crawl_times(days=days)
    if len(crawl_times) < 2:
        return {}

    latest = crawl_times[-1]
    earliest = crawl_times[0]

    latest_cats = get_category_stats(platform, chart_type, latest)
    earliest_cats = get_category_stats(platform, chart_type, earliest)

    latest_map = {c['category']: c for c in latest_cats}
    earliest_map = {c['category']: c for c in earliest_cats}

    trends = []
    all_cats = set(list(latest_map.keys()) + list(earliest_map.keys()))

    for cat in all_cats:
        if not cat:
            continue
        now_count = latest_map.get(cat, {}).get('count', 0)
        then_count = earliest_map.get(cat, {}).get('count', 0)
        diff = now_count - then_count

        trends.append({
            'category': cat,
            'current_count': now_count,
            'previous_count': then_count,
            'change': diff,
            'avg_rank': latest_map.get(cat, {}).get('avg_rank'),
        })

    trends.sort(key=lambda x: x['change'], reverse=True)
    return trends


def find_consecutive_risers(platform, chart_type, days=7, min_rises=3):
    """Find apps that have been rising consistently"""
    conn = get_db()
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    # Get all apps that appear in recent crawls
    rows = conn.execute("""
        SELECT app_id, app_name, category,
               GROUP_CONCAT(rank || ':' || crawl_time, '|') as history
        FROM rankings
        WHERE platform=? AND chart_type=? AND crawl_time>=?
        GROUP BY app_id
        HAVING COUNT(*) >= ?
        ORDER BY app_name
    """, (platform, chart_type, since, min_rises)).fetchall()
    conn.close()

    risers = []
    for row in rows:
        history = row['history'].split('|')
        points = []
        for h in history:
            parts = h.split(':', 1)
            if len(parts) == 2:
                points.append((parts[1], int(parts[0])))
        points.sort(key=lambda x: x[0])  # Sort by time

        # Check if consistently rising (rank decreasing)
        if len(points) >= min_rises:
            consecutive = 0
            max_consecutive = 0
            for i in range(1, len(points)):
                if points[i][1] < points[i-1][1]:  # Rank went down = moved up
                    consecutive += 1
                    max_consecutive = max(max_consecutive, consecutive)
                else:
                    consecutive = 0

            if max_consecutive >= min_rises - 1:
                first_rank = points[0][1]
                last_rank = points[-1][1]
                risers.append({
                    'app_id': row['app_id'],
                    'app_name': row['app_name'],
                    'category': row['category'],
                    'first_rank': first_rank,
                    'current_rank': last_rank,
                    'total_rise': first_rank - last_rank,
                    'data_points': len(points),
                    'consecutive_rises': max_consecutive,
                })

    risers.sort(key=lambda x: x['total_rise'], reverse=True)
    return risers


def generate_full_analysis(crawl_time=None):
    """Generate complete analysis for all charts"""
    if not crawl_time:
        crawl_time = get_latest_crawl_time()
    if not crawl_time:
        return None

    analysis = {
        'crawl_time': crawl_time,
        'charts': {},
        'category_trends': {},
        'consecutive_risers': {},
    }

    for platform in ['gp', 'ios']:
        for chart_type in ['free', 'paid', 'grossing']:
            key = f"{platform}_{chart_type}"

            prev_time = get_previous_crawl_time(crawl_time, platform)
            changes = analyze_chart_changes(platform, chart_type, crawl_time, prev_time)
            analysis['charts'][key] = {
                'changes': changes,
                'previous_time': prev_time,
            }

            cat_trends = analyze_category_trends(platform, chart_type)
            analysis['category_trends'][key] = cat_trends

            risers = find_consecutive_risers(platform, chart_type)
            analysis['consecutive_risers'][key] = risers

    return analysis


if __name__ == "__main__":
    analysis = generate_full_analysis()
    if analysis:
        print(f"Analysis for crawl at {analysis['crawl_time']}")
        for key, data in analysis['charts'].items():
            changes = data['changes']
            print(f"\n--- {key} ---")
            print(f"  New entries: {len(changes['new_entries'])}")
            print(f"  Surges (≥{RANK_SURGE_THRESHOLD}): {len(changes['surges'])}")
            print(f"  Drops (≥{RANK_SURGE_THRESHOLD}): {len(changes['drops'])}")
            print(f"  Exits: {len(changes['exits'])}")
    else:
        print("No data to analyze. Run crawler first.")
