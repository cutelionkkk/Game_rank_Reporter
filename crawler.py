"""Country- and genre-qualified game rankings. Failed responses stay failures."""
import json
import time
from config import load_settings, chart_scopes
from database import insert_rankings, log_crawl, init_db, utcnow
from genres import get_genre, format_chart_label
from store_api import fetch_json, run_gp


def crawl_gp_chart(chart_type, genre_id='all', country=None, top_n=None):
    settings = load_settings()
    genre = get_genre(genre_id)
    if not genre or not genre.get('gp_category'):
        raise ValueError('Google Play 不支持该品类')
    return run_gp(chart_type, country or settings['country'], genre['gp_category'], top_n or settings['top_n'])


def _ios_old_rss_url(chart_type, genre_id, country, top_n):
    feed = {'free': 'topfreeapplications', 'paid': 'toppaidapplications',
            'grossing': 'topgrossingapplications'}.get(chart_type)
    genre = get_genre(genre_id)
    if not feed or not genre or not genre.get('ios_genre_id'):
        raise ValueError('App Store 不支持该榜单/品类组合')
    return f"https://itunes.apple.com/{country}/rss/{feed}/limit={top_n}/genre={genre['ios_genre_id']}/json"


def _parse_ios_old(data, top_n=100):
    entries = data.get('feed', {}).get('entry', [])
    if isinstance(entries, dict):
        entries = [entries]
    results = []
    for i, entry in enumerate(entries[:top_n], 1):
        app_id = entry.get('id', {}).get('attributes', {}).get('im:id')
        name = entry.get('im:name', {}).get('label')
        if not app_id or not name:
            raise ValueError('App Store 榜单信息不完整')
        images = entry.get('im:image', [])
        links = entry.get('link', [])
        if isinstance(links, dict):
            links = [links]
        url = next((x.get('attributes', {}).get('href', '') for x in links
                    if x.get('attributes', {}).get('rel') == 'alternate'), '')
        results.append(dict(rank=i, app_id=str(app_id), app_name=name,
                            developer=entry.get('im:artist', {}).get('label', ''),
                            category=entry.get('category', {}).get('attributes', {}).get('label', ''),
                            icon_url=images[-1].get('label', '') if images else '',
                            extra_json=json.dumps(dict(url=url,
                                releaseDate=entry.get('im:releaseDate', {}).get('label', '')))))
    return results


def crawl_ios_chart(chart_type, genre_id='all', country=None, top_n=None):
    settings = load_settings()
    country, top_n = country or settings['country'], top_n or settings['top_n']
    # RSS v2 has an all-apps chart, not a game chart. Never substitute it.
    data = fetch_json(_ios_old_rss_url(chart_type, genre_id, country, top_n))
    return _parse_ios_old(data, top_n)


def _get_chart_list():
    return chart_scopes()


def run_full_crawl(crawl_time=None, settings=None):
    init_db()
    crawl_time = crawl_time or utcnow()
    settings = settings if settings is not None else load_settings()
    total, errors = 0, []
    for scope in chart_scopes(settings):
        platform, chart, genre, country = (scope[k] for k in ('platform', 'chart_type', 'genre', 'country'))
        key = chart if genre == 'all' else f'{chart}:{genre}'
        label = country.upper() + ' ' + format_chart_label(platform, chart, genre)
        started = time.monotonic()
        try:
            crawl = crawl_ios_chart if platform == 'ios' else crawl_gp_chart
            apps = crawl(chart, genre, country, settings['top_n'])
            if not apps:
                raise ValueError('来源未返回榜单，可能不支持该地区/品类/榜单；未改用其他榜单')
            count = insert_rankings(crawl_time, platform, key, apps, country)
            log_crawl(crawl_time, platform, key, count, 'ok', duration=time.monotonic()-started, country=country)
            total += count
            print(f'✅ {label}: {count} 款')
        except Exception as exc:
            error = str(exc)[:600]
            log_crawl(crawl_time, platform, key, 0, 'error', error, time.monotonic()-started, country)
            errors.append(f'{label}: {error}')
            print(f'⚠️ {label}: {error}')
    return crawl_time, total, errors


if __name__ == '__main__':
    run_full_crawl()
