"""Watch developer catalogs independently of chart membership."""
import json
from datetime import datetime, timezone
from database import get_db, query, parse_time
from store_api import fetch_publisher


def release_age_days(value, at):
    """Store release dates only. Unknown/future dates never imply a new release."""
    if not value:
        return None
    try:
        date = parse_time(value)
    except (ValueError, TypeError):
        date = None
        for fmt in ('%b %d, %Y', '%B %d, %Y'):
            try:
                date = datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
                break
            except (ValueError, TypeError):
                pass
        if date is None:
            return None
    return (parse_time(at) - date).total_seconds() / 86400


def enabled_companies(settings):
    return [c for c in settings.get('companies', []) if c.get('enabled', True)] if settings.get('company_enabled', True) else []


def store_catalog(crawl_time, company, country, catalog, new_days):
    """Commit catalog and events atomically; first successful catalog is silent."""
    platform, dev = company['platform'], company['developer_id']
    apps = catalog['apps']
    if not apps or len({a['app_id'] for a in apps}) != len(apps):
        raise ValueError('开发者目录为空或存在重复产品，保留原基线')
    conn = get_db()
    try:
        with conn:
            conn.execute('BEGIN IMMEDIATE')
            baseline = not conn.execute('''SELECT 1 FROM publisher_snapshots
                WHERE platform=? AND developer_id=? AND country=? AND status IN ('ok','partial') LIMIT 1''',
                (platform,dev,country)).fetchone()
            known_anywhere = {r[0] for r in conn.execute('''SELECT DISTINCT app_id FROM publisher_apps
                WHERE platform=? AND developer_id=?''', (platform,dev))}
            new_events = 0
            for app in apps:
                data = json.dumps(app, ensure_ascii=False)
                age = release_age_days(app.get('release_date'), crawl_time)
                if not baseline and app['app_id'] not in known_anywhere and app.get('is_game'):
                    kind = 'new_release' if age is not None and 0 <= age <= new_days else 'newly_discovered'
                    cursor = conn.execute('''INSERT OR IGNORE INTO publisher_events
                        (platform,developer_id,app_id,crawl_time,country,kind,data_json) VALUES (?,?,?,?,?,?,?)''',
                        (platform,dev,app['app_id'],crawl_time,country,kind,data))
                    new_events += cursor.rowcount
                conn.execute('''INSERT INTO publisher_apps
                    (platform,developer_id,country,app_id,app_name,release_date,first_seen,last_seen,data_json)
                    VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(platform,developer_id,country,app_id)
                    DO UPDATE SET app_name=excluded.app_name,release_date=excluded.release_date,
                                  last_seen=excluded.last_seen,data_json=excluded.data_json''',
                    (platform,dev,country,app['app_id'],app['app_name'],app.get('release_date'),crawl_time,crawl_time,data))
            conn.execute('''INSERT OR REPLACE INTO publisher_snapshots
                (crawl_time,platform,developer_id,country,status,count,baseline,message) VALUES (?,?,?,?,?,?,?,?)''',
                (crawl_time,platform,dev,country,'partial' if catalog.get('partial') else 'ok',
                 sum(bool(a.get('is_game')) for a in apps),int(baseline),catalog.get('message', '')))
        return new_events
    finally:
        conn.close()


def crawl_companies(crawl_time, settings):
    total, errors = 0, []
    for company in enabled_companies(settings):
        for country in company['countries']:
            p, dev = company['platform'], company['developer_id']
            try:
                known = {r['app_id']: json.loads(r['data_json']) for r in query(
                    'SELECT app_id,data_json FROM publisher_apps WHERE platform=? AND developer_id=? AND country=?',
                    (p,dev,country))}
                catalog = fetch_publisher(company, country, known)
                store_catalog(crawl_time, company, country, catalog, settings['new_entry_days'])
                total += 1
                print(f"✅ {company['name']} · {country.upper()}: {len(catalog['apps'])} 款产品")
            except Exception as exc:
                message = str(exc)[:600]
                with get_db() as conn:
                    conn.execute('''INSERT OR REPLACE INTO publisher_snapshots
                        (crawl_time,platform,developer_id,country,status,count,message)
                        VALUES (?,?,?,?,'error',0,?)''', (crawl_time,p,dev,country,message))
                conn.close()
                errors.append(f"{company['name']} · {country.upper()}: {message}")
    return total, errors


def company_analysis(crawl_time, settings):
    result = []
    for company in enabled_companies(settings):
        p, dev = company['platform'], company['developer_id']
        snapshots = query('SELECT * FROM publisher_snapshots WHERE crawl_time=? AND platform=? AND developer_id=?',
                          (crawl_time,p,dev))
        snapshots = [s for s in snapshots if s['country'] in company['countries']]
        events = query('SELECT * FROM publisher_events WHERE crawl_time=? AND platform=? AND developer_id=?',
                       (crawl_time,p,dev))
        events = [dict(json.loads(e['data_json']), kind=e['kind'], country=e['country'],
                       first_seen=e['crawl_time']) for e in events if e['country'] in company['countries']]
        events.sort(key=lambda e: (e['kind'] != 'new_release', e['app_name']))
        result.append(dict(company=company, snapshots=snapshots, events=events))
    return result
