"""SQLite storage. Each ranking and publisher baseline belongs to a country."""
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from config import DB_PATH, load_settings


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def parse_time(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA foreign_keys=ON')
    return conn


RANK_SCHEMA = '''CREATE TABLE rankings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    crawl_time TEXT NOT NULL, platform TEXT NOT NULL, country TEXT NOT NULL,
    chart_type TEXT NOT NULL, rank INTEGER NOT NULL,
    app_id TEXT NOT NULL, app_name TEXT NOT NULL,
    developer TEXT, category TEXT, rating REAL, rating_count INTEGER,
    price REAL, icon_url TEXT, extra_json TEXT,
    UNIQUE(crawl_time, platform, country, chart_type, rank)
)'''


def init_db():
    conn = get_db()
    try:
        columns = {r['name'] for r in conn.execute('PRAGMA table_info(rankings)')}
        if columns and 'country' not in columns:
            # Preserve a recoverable copy before rebuilding the old uniqueness constraint.
            backup_path = DB_PATH + '.pre-country.bak'
            if not os.path.exists(backup_path):
                with sqlite3.connect(backup_path) as backup:
                    conn.backup(backup)
        with conn:
            conn.execute('BEGIN IMMEDIATE')
            # Re-read under the write lock in case another process just migrated it.
            columns = {r['name'] for r in conn.execute('PRAGMA table_info(rankings)')}
            if columns and 'country' not in columns:
                conn.execute('ALTER TABLE rankings RENAME TO rankings_legacy')
                conn.execute(RANK_SCHEMA)
                names = ('id,crawl_time,platform,chart_type,rank,app_id,app_name,'
                         'developer,category,rating,rating_count,price,icon_url,extra_json')
                conn.execute(f'INSERT INTO rankings ({names},country) '
                             f'SELECT {names},? FROM rankings_legacy',
                             (load_settings().get('country', 'us').lower(),))
                conn.execute('DROP TABLE rankings_legacy')
            elif not columns:
                conn.execute(RANK_SCHEMA)
            conn.execute('CREATE INDEX IF NOT EXISTS idx_rank_scope ON rankings '
                         '(platform,country,chart_type,crawl_time)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_rank_app ON rankings(app_id,platform,country)')
            conn.execute('''CREATE TABLE IF NOT EXISTS crawl_log (
                id INTEGER PRIMARY KEY, crawl_time TEXT NOT NULL,
                platform TEXT NOT NULL, country TEXT NOT NULL DEFAULT 'us',
                chart_type TEXT NOT NULL, count INTEGER NOT NULL,
                status TEXT NOT NULL, message TEXT, duration_sec REAL)''')
            if 'country' not in {r['name'] for r in conn.execute('PRAGMA table_info(crawl_log)')}:
                conn.execute("ALTER TABLE crawl_log ADD COLUMN country TEXT NOT NULL DEFAULT 'us'")
                conn.execute('UPDATE crawl_log SET country=?', (load_settings().get('country', 'us').lower(),))
            conn.execute('''CREATE TABLE IF NOT EXISTS monitor_runs (
                crawl_time TEXT PRIMARY KEY, finished_at TEXT, status TEXT NOT NULL,
                settings_json TEXT NOT NULL, error TEXT)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS publisher_snapshots (
                crawl_time TEXT NOT NULL, platform TEXT NOT NULL, developer_id TEXT NOT NULL,
                country TEXT NOT NULL, status TEXT NOT NULL, count INTEGER NOT NULL,
                baseline INTEGER NOT NULL DEFAULT 0, message TEXT,
                PRIMARY KEY(crawl_time,platform,developer_id,country))''')
            conn.execute('''CREATE TABLE IF NOT EXISTS publisher_apps (
                platform TEXT NOT NULL, developer_id TEXT NOT NULL, country TEXT NOT NULL,
                app_id TEXT NOT NULL, app_name TEXT NOT NULL, release_date TEXT,
                first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, data_json TEXT NOT NULL,
                PRIMARY KEY(platform,developer_id,country,app_id))''')
            conn.execute('''CREATE TABLE IF NOT EXISTS publisher_events (
                platform TEXT NOT NULL, developer_id TEXT NOT NULL, app_id TEXT NOT NULL,
                crawl_time TEXT NOT NULL, country TEXT NOT NULL, kind TEXT NOT NULL,
                data_json TEXT NOT NULL,
                PRIMARY KEY(platform,developer_id,app_id))''')
    finally:
        conn.close()


def insert_rankings(crawl_time, platform, chart_type, items, country=None):
    country = country or load_settings().get('country', 'us')
    if not items or len({str(a['app_id']) for a in items}) != len(items):
        raise ValueError('榜单为空或包含重复应用，未写入快照')
    if [a['rank'] for a in items] != list(range(1, len(items) + 1)):
        raise ValueError('榜单名次不连续，未写入快照')
    with get_db() as conn:
        conn.executemany('''INSERT OR REPLACE INTO rankings
            (crawl_time,platform,country,chart_type,rank,app_id,app_name,developer,
             category,rating,rating_count,price,icon_url,extra_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', [
                (crawl_time,platform,country,chart_type,a['rank'],str(a['app_id']),a['app_name'],
                 a.get('developer'),a.get('category'),a.get('rating'),a.get('rating_count'),
                 a.get('price'),a.get('icon_url'),a.get('extra_json')) for a in items])
    conn.close()
    return len(items)


def log_crawl(crawl_time, platform, chart_type, count, status, message=None, duration=None, country=None):
    with get_db() as conn:
        conn.execute('''INSERT INTO crawl_log
            (crawl_time,platform,country,chart_type,count,status,message,duration_sec)
            VALUES (?,?,?,?,?,?,?,?)''',
            (crawl_time,platform,country or load_settings().get('country', 'us'),chart_type,
             count,status,message,duration))
    conn.close()


def query(sql, params=()):
    conn = get_db()
    try:
        return [dict(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


def get_latest_crawl_time(platform=None):
    rows = query('SELECT crawl_time AS t FROM rankings' +
                 (' WHERE platform=?' if platform else '') + ' ORDER BY julianday(crawl_time) DESC LIMIT 1', (platform,) if platform else ())
    return rows[0]['t'] if rows else None


def get_latest_run_time():
    rows = query('''SELECT crawl_time AS t FROM (
        SELECT crawl_time FROM monitor_runs UNION ALL SELECT crawl_time FROM rankings
        UNION ALL SELECT crawl_time FROM crawl_log UNION ALL SELECT crawl_time FROM publisher_snapshots)
        ORDER BY julianday(crawl_time) DESC LIMIT 1''')
    return rows[0]['t'] if rows else None


def get_rankings_at(crawl_time, platform, chart_type, country=None):
    return query('''SELECT * FROM rankings WHERE crawl_time=? AND platform=?
                    AND country=? AND chart_type=? ORDER BY rank''',
                 (crawl_time, platform, country or load_settings().get('country', 'us'), chart_type))


def get_previous_crawl_time(current_time, platform=None, chart_type=None, country=None, hours=0):
    conditions, params = ['julianday(crawl_time) < julianday(?)'], [current_time]
    if platform:
        conditions.append('platform=?'); params.append(platform)
    if chart_type:
        conditions.append('chart_type=?'); params.append(chart_type)
    if platform or country:
        conditions.append('country=?'); params.append(country or load_settings().get('country', 'us'))
    if hours:
        # Use the latest successful snapshot at or before the requested horizon.
        cutoff = (parse_time(current_time) - timedelta(hours=hours)).isoformat().replace('+00:00', 'Z')
        conditions.append('julianday(crawl_time)<=julianday(?)'); params.append(cutoff)
    rows = query('SELECT crawl_time AS t FROM rankings WHERE ' + ' AND '.join(conditions) +
                 ' ORDER BY julianday(crawl_time) DESC LIMIT 1', params)
    return rows[0]['t'] if rows else None


def get_all_chart_types_at(crawl_time):
    """Legacy single-country API used by the metadata enrichment command."""
    return [(r['platform'], r['chart_type']) for r in query(
        'SELECT DISTINCT platform,chart_type FROM rankings WHERE crawl_time=? AND country=?',
        (crawl_time, load_settings().get('country', 'us')))]


def get_app_rank_history(app_id, platform, chart_type, days=7, country=None):
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    return query('''SELECT crawl_time,rank FROM rankings WHERE app_id=? AND platform=?
        AND country=? AND chart_type=? AND julianday(crawl_time)>=julianday(?) ORDER BY crawl_time''',
        (app_id,platform,country or load_settings().get('country', 'us'),chart_type,since))


def get_category_stats(platform, chart_type, crawl_time, country=None):
    return query('''SELECT category,COUNT(*) AS count,AVG(rank) AS avg_rank FROM rankings
        WHERE platform=? AND country=? AND chart_type=? AND crawl_time=? AND category IS NOT NULL
        GROUP BY category ORDER BY count DESC''',
        (platform,country or load_settings().get('country', 'us'),chart_type,crawl_time))


def get_all_crawl_times(days=7):
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    return [r['crawl_time'] for r in query('''SELECT DISTINCT crawl_time FROM rankings
        WHERE julianday(crawl_time)>=julianday(?) ORDER BY crawl_time''', (since,))]


if __name__ == '__main__':
    init_db()
    print(f'Database initialized at {DB_PATH}')
