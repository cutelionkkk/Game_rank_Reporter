"""Database layer for game rankings storage"""

import sqlite3
import os
from datetime import datetime, timedelta
from config import DB_PATH


def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Initialize database schema"""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS rankings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            crawl_time TEXT NOT NULL,           -- ISO 8601 timestamp
            platform TEXT NOT NULL,             -- 'gp' or 'ios'
            chart_type TEXT NOT NULL,           -- 'free', 'paid', 'grossing'
            rank INTEGER NOT NULL,             -- 1-100
            app_id TEXT NOT NULL,              -- bundle id / package name
            app_name TEXT NOT NULL,
            developer TEXT,
            category TEXT,
            rating REAL,
            rating_count INTEGER,
            price REAL,
            icon_url TEXT,
            extra_json TEXT,                   -- JSON blob for platform-specific data
            UNIQUE(crawl_time, platform, chart_type, rank)
        );

        CREATE INDEX IF NOT EXISTS idx_rankings_time
            ON rankings(crawl_time);
        CREATE INDEX IF NOT EXISTS idx_rankings_app
            ON rankings(app_id, platform);
        CREATE INDEX IF NOT EXISTS idx_rankings_lookup
            ON rankings(platform, chart_type, crawl_time);
        CREATE INDEX IF NOT EXISTS idx_rankings_category
            ON rankings(category, crawl_time);

        CREATE TABLE IF NOT EXISTS crawl_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            crawl_time TEXT NOT NULL,
            platform TEXT NOT NULL,
            chart_type TEXT NOT NULL,
            count INTEGER NOT NULL,
            status TEXT NOT NULL,              -- 'ok' or 'error'
            message TEXT,
            duration_sec REAL
        );
    """)
    conn.commit()
    conn.close()


def insert_rankings(crawl_time, platform, chart_type, items):
    """Insert a batch of ranking entries"""
    conn = get_db()
    conn.executemany("""
        INSERT OR REPLACE INTO rankings
        (crawl_time, platform, chart_type, rank, app_id, app_name,
         developer, category, rating, rating_count, price, icon_url, extra_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        (crawl_time, platform, chart_type,
         item['rank'], item['app_id'], item['app_name'],
         item.get('developer'), item.get('category'),
         item.get('rating'), item.get('rating_count'),
         item.get('price'), item.get('icon_url'),
         item.get('extra_json'))
        for item in items
    ])
    conn.commit()
    conn.close()
    return len(items)


def log_crawl(crawl_time, platform, chart_type, count, status, message=None, duration=None):
    """Log a crawl attempt"""
    conn = get_db()
    conn.execute("""
        INSERT INTO crawl_log (crawl_time, platform, chart_type, count, status, message, duration_sec)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (crawl_time, platform, chart_type, count, status, message, duration))
    conn.commit()
    conn.close()


def get_latest_crawl_time(platform=None):
    """Get the most recent crawl time"""
    conn = get_db()
    if platform:
        row = conn.execute(
            "SELECT MAX(crawl_time) as t FROM rankings WHERE platform=?", (platform,)
        ).fetchone()
    else:
        row = conn.execute("SELECT MAX(crawl_time) as t FROM rankings").fetchone()
    conn.close()
    return row['t'] if row else None


def get_rankings_at(crawl_time, platform, chart_type):
    """Get rankings for a specific crawl"""
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM rankings
        WHERE crawl_time=? AND platform=? AND chart_type=?
        ORDER BY rank
    """, (crawl_time, platform, chart_type)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_previous_crawl_time(current_time, platform=None, chart_type=None):
    """Get the crawl time before the given time"""
    conn = get_db()
    if platform and chart_type:
        row = conn.execute("""
            SELECT MAX(crawl_time) as t FROM rankings
            WHERE crawl_time < ? AND platform=? AND chart_type=?
        """, (current_time, platform, chart_type)).fetchone()
    elif platform:
        row = conn.execute("""
            SELECT MAX(crawl_time) as t FROM rankings
            WHERE crawl_time < ? AND platform=?
        """, (current_time, platform)).fetchone()
    else:
        row = conn.execute("""
            SELECT MAX(crawl_time) as t FROM rankings
            WHERE crawl_time < ?
        """, (current_time,)).fetchone()
    conn.close()
    return row['t'] if row else None


def get_all_chart_types_at(crawl_time):
    """Get all (platform, chart_type) pairs present at a given crawl_time"""
    conn = get_db()
    rows = conn.execute("""
        SELECT DISTINCT platform, chart_type FROM rankings
        WHERE crawl_time=?
        ORDER BY platform, chart_type
    """, (crawl_time,)).fetchall()
    conn.close()
    return [(r['platform'], r['chart_type']) for r in rows]


def get_app_rank_history(app_id, platform, chart_type, days=7):
    """Get rank history for an app over N days"""
    conn = get_db()
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    rows = conn.execute("""
        SELECT crawl_time, rank FROM rankings
        WHERE app_id=? AND platform=? AND chart_type=? AND crawl_time>=?
        ORDER BY crawl_time
    """, (app_id, platform, chart_type, since)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_category_stats(platform, chart_type, crawl_time):
    """Get category distribution for a crawl"""
    conn = get_db()
    rows = conn.execute("""
        SELECT category, COUNT(*) as count, AVG(rank) as avg_rank
        FROM rankings
        WHERE platform=? AND chart_type=? AND crawl_time=? AND category IS NOT NULL
        GROUP BY category
        ORDER BY count DESC
    """, (platform, chart_type, crawl_time)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_crawl_times(days=7):
    """Get all distinct crawl times in the last N days"""
    conn = get_db()
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    rows = conn.execute("""
        SELECT DISTINCT crawl_time FROM rankings
        WHERE crawl_time >= ?
        ORDER BY crawl_time
    """, (since,)).fetchall()
    conn.close()
    return [r['crawl_time'] for r in rows]


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")
