"""Analysis shared by the dashboard, reports and JSON export."""
import json
from collections import Counter
from config import load_settings, chart_scopes
from database import (get_rankings_at, get_previous_crawl_time, get_latest_run_time,
                      parse_time, query, init_db)
from publishers import company_analysis, release_age_days


def analyze_chart_changes(platform, chart_type, current_time, previous_time, country=None, settings=None):
    s = settings if settings is not None else load_settings()
    current = get_rankings_at(current_time,platform,chart_type,country)
    previous = get_rankings_at(previous_time,platform,chart_type,country) if previous_time else []
    changes = {key: [] for key in ('new_entries','surges','drops','exits','top_movers_up','top_movers_down','stable_top')}
    if not current or not previous:
        return changes
    prev_map, curr_map = ({a['app_id']: a for a in apps} for apps in (previous,current))
    # Different crawl depths must not manufacture entries/exits.
    common_depth = min(max(a['rank'] for a in current), max(a['rank'] for a in previous))
    threshold = s['rank_surge_threshold']
    for app in current:
        old = prev_map.get(app['app_id'])
        if old:
            diff = old['rank'] - app['rank']
            item = dict(app,prev_rank=old['rank'],rank_change=diff)
            if diff >= threshold:
                changes['surges'].append(item)
            elif diff <= -threshold:
                changes['drops'].append(item)
            if diff:
                changes['top_movers_up' if diff > 0 else 'top_movers_down'].append(item)
            elif app['rank'] <= 10:
                changes['stable_top'].append(app)
        elif app['rank'] <= common_depth:
            try:
                release = json.loads(app.get('extra_json') or '{}').get('releaseDate')
            except (ValueError, AttributeError):
                release = None
            age = release_age_days(release,current_time)
            changes['new_entries'].append(dict(app,is_new_game=age is not None and 0 <= age <= s['new_entry_days']))
    changes['exits'] = [a for a in previous if a['app_id'] not in curr_map and a['rank'] <= common_depth]
    for key in ('surges','top_movers_up','drops','top_movers_down'):
        changes[key].sort(key=lambda a: (-abs(a['rank_change']),a['rank']))
    return changes


def find_consecutive_risers(platform, chart_type, days=7, min_rises=3, country=None, current_time=None):
    """Count consecutive observations ending at the latest successful snapshot."""
    if not current_time:
        return []
    rows = query('''SELECT crawl_time,app_id,app_name,rank FROM rankings
        WHERE platform=? AND country=? AND chart_type=? AND julianday(crawl_time)<=julianday(?)
        AND julianday(crawl_time)>=julianday(?)-? ORDER BY crawl_time''',
        (platform,country or load_settings()['country'],chart_type,current_time,current_time,days))
    times = sorted({r['crawl_time'] for r in rows})
    histories = {}
    for row in rows:
        histories.setdefault(row['app_id'], {})[row['crawl_time']] = row
    result = []
    for history in histories.values():
        if current_time not in history:
            continue
        streak = 0
        for a,b in zip(reversed(times[:-1]),reversed(times[1:])):
            if a not in history or b not in history or history[a]['rank'] <= history[b]['rank']:
                break
            streak += 1
        if streak >= min_rises:
            current = history[current_time]
            first = history[times[-1-streak]]['rank']
            result.append(dict(app_id=current['app_id'],app_name=current['app_name'],
                               current_rank=current['rank'],first_rank=first,total_rise=first-current['rank'],
                               consecutive_rises=streak))
    return sorted(result,key=lambda a:-a['total_rise'])


def generate_full_analysis(crawl_time=None, settings=None):
    init_db()
    s = settings if settings is not None else load_settings()
    crawl_time = crawl_time or get_latest_run_time()
    if not crawl_time:
        return None
    analysis = dict(crawl_time=crawl_time, charts={}, category_trends={}, consecutive_risers={},
                    companies=company_analysis(crawl_time,s), errors=[])
    run = query('SELECT status,finished_at,error FROM monitor_runs WHERE crawl_time=?', (crawl_time,))
    analysis['run'] = run[0] if run else {'status':'legacy'}
    for scope in chart_scopes(s):
        p, country, chart, genre = (scope[k] for k in ('platform','country','chart_type','genre'))
        db_chart = chart if genre == 'all' else f'{chart}:{genre}'
        key = f'{p}_{country}_{db_chart}'
        current = get_rankings_at(crawl_time,p,db_chart,country)
        logs = query('''SELECT status,message,count FROM crawl_log WHERE crawl_time=? AND platform=?
                        AND country=? AND chart_type=? ORDER BY id DESC LIMIT 1''', (crawl_time,p,country,db_chart))
        status = logs[0]['status'] if logs else 'ok' if current else 'not_run'
        message = logs[0].get('message') if logs else ''
        if status != 'ok':
            current = []
        prev = get_previous_crawl_time(crawl_time,p,db_chart,country,s['comparison_hours']) if current else None
        elapsed = (parse_time(crawl_time)-parse_time(prev)).total_seconds()/3600 if prev else None
        if prev and s['comparison_hours'] and elapsed > s['comparison_hours'] * 2:
            prev, elapsed = None, None  # stale history isn't a rapid rise
        changes = analyze_chart_changes(p,db_chart,crawl_time,prev,country,s) if current else {}
        item = dict(scope=scope,db_chart_type=db_chart,status=status,message=message,current=current,
                    previous_time=prev,elapsed_hours=round(elapsed,1) if elapsed is not None else None,
                    threshold=s['rank_surge_threshold'],comparison_hours=s['comparison_hours'],changes=changes)
        analysis['charts'][key] = item
        if status == 'error':
            analysis['errors'].append(dict(scope=scope,message=message))
        if prev:
            before = Counter(a['category'] for a in get_rankings_at(prev,p,db_chart,country))
            after = Counter(a['category'] for a in current)
            analysis['category_trends'][key] = [dict(category=cat,current_count=after[cat],
                previous_count=before[cat],change=after[cat]-before[cat]) for cat in sorted(set(before)|set(after),key=str) if cat]
        if current:
            analysis['consecutive_risers'][key] = find_consecutive_risers(p,db_chart,
                days=s['category_trend_window'],min_rises=s['consecutive_rise_days'],country=country,current_time=crawl_time)
    return analysis
