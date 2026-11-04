"""Small, bounded adapters for public store data. No credentials required."""
import json
import os
import subprocess
from urllib.parse import urlencode
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = os.path.dirname(os.path.abspath(__file__))


def fetch_json(url, params=None):
    with requests.Session() as session:
        session.mount('https://', HTTPAdapter(max_retries=Retry(
            total=2, backoff_factor=0.6, status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=('GET',), respect_retry_after_header=False)))
        response = session.get(url, params=params, timeout=(10, 25),
                               headers={'User-Agent': 'GameRankReporter/2.0'})
        response.raise_for_status()
        return response.json()


def run_gp(mode, country, value, limit=100, known=None):
    if not os.path.isdir(os.path.join(ROOT, 'node_modules', 'google-play-scraper')):
        raise RuntimeError('Google Play 依赖未安装，请在项目目录运行 npm ci')
    try:
        result = subprocess.run(['node', os.path.join(ROOT, 'gp_scraper.js'), mode,
                                 country, str(limit), value],
                                input=json.dumps(known or {}), capture_output=True,
                                text=True, timeout=240 if mode == 'developer' else 120)
    except FileNotFoundError as exc:
        raise RuntimeError('Google Play 需要 Node.js 22 或更新版本') from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError('Google Play 请求超时，本轮未写入快照') from exc
    if result.returncode:
        raise RuntimeError('Google Play: ' + result.stderr.strip()[-600:])
    return json.loads(result.stdout)


def developer_url(platform, developer_id, country):
    if platform == 'ios':
        return f'https://apps.apple.com/{country}/developer/id{developer_id}'
    path = 'dev' if developer_id.isdigit() else 'developer'
    return 'https://play.google.com/store/apps/' + path + '?' + urlencode({'id': developer_id, 'gl': country})


def ios_game(app):
    return '6014' in [str(g) for g in app.get('genreIds', [])] or app.get('primaryGenreId') == 6014


def search_companies(platform, country, term):
    """Return candidate accounts, never auto-follow a name match."""
    from config import country_code
    country = country_code(country)
    if platform not in ('ios', 'gp') or not isinstance(term, str) or not 2 <= len(term.strip()) <= 100:
        raise ValueError('请选择商店，并输入 2–100 字的公司名或游戏名')
    term = term.strip()
    if platform == 'ios':
        data = fetch_json('https://itunes.apple.com/search',
                          dict(term=term, country=country, entity='software', limit=50))
        apps = [dict(developer_id=str(a['artistId']), name=a.get('artistName', ''),
                     example=a.get('trackName', '')) for a in data.get('results', [])
                if a.get('artistId') and ios_game(a)]
    else:
        apps = run_gp('search', country, term, 20)
    accounts = {}
    for app in apps:
        dev_id = app.get('developer_id')
        if not dev_id:
            continue
        key = str(dev_id)
        if key not in accounts:
            accounts[key] = dict(platform=platform, developer_id=key, name=app['name'],
                                 country=country, examples=[], url=developer_url(platform, key, country))
        if app.get('example') and len(accounts[key]['examples']) < 3:
            accounts[key]['examples'].append(app['example'])
    return sorted(accounts.values(), key=lambda c: (term.casefold() not in c['name'].casefold(), c['name'].casefold()))


def fetch_publisher(company, country, known=None):
    dev_id, platform = company['developer_id'], company['platform']
    if platform == 'gp':
        return run_gp('developer', country, dev_id, 200, known)
    data = fetch_json('https://itunes.apple.com/lookup',
                      dict(id=dev_id, entity='software', country=country, limit=200))
    if not isinstance(data.get('results'), list):
        raise ValueError('App Store 开发者接口返回格式无效')
    # An empty/invalid developer response must never establish a baseline.
    results = data['results']
    apps = []
    for a in results:
        if a.get('wrapperType') != 'software' or str(a.get('artistId')) != dev_id:
            continue
        if not a.get('trackId') or not a.get('trackName'):
            raise ValueError('App Store 产品信息不完整')
        apps.append(dict(app_id=str(a['trackId']), app_name=a['trackName'],
                         developer=a.get('artistName', ''), release_date=a.get('releaseDate'),
                         is_game=ios_game(a), category=a.get('primaryGenreName', ''),
                         url=a.get('trackViewUrl', ''), icon_url=a.get('artworkUrl100', '')))
    if not apps:
        raise ValueError('未取得该开发者的产品；请核对开发者 ID 和国家，原有基线已保留')
    return dict(apps=apps, partial=len(apps) >= 199,
                message='App Store 单个开发者最多返回约 200 款产品，可能不完整' if len(apps) >= 199 else '')
