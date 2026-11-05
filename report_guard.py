"""Fail closed before delivering reports; collection success alone is insufficient."""
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

from analyzer import generate_full_analysis
from config import load_settings, monitor_settings
from database import get_latest_run_time, get_rankings_at, parse_time, query
from product_links import product_url

VERSION = 1
MAX_AGE_HOURS = 3


class ReportBlocked(RuntimeError):
    """Safe, non-private reason suitable for public workflow logs."""


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.active = None

    def handle_starttag(self, tag, attrs):
        if tag in ('a', 'link'):
            self.active = [dict(attrs).get('href' if tag == 'a' else 'url', ''), '']

    def handle_data(self, data):
        if self.active is not None:
            self.active[1] += data

    def handle_endtag(self, tag):
        if tag in ('a', 'link') and self.active is not None:
            self.links.append(tuple(self.active))
            self.active = None


def validate_report(parts, day, trial=False, crawl_time=None, now=None):
    """Validate the actual source, selected coverage and exact rendered report."""
    crawl_time = crawl_time or get_latest_run_time()
    if not crawl_time:
        raise ReportBlocked('发送检查未通过：没有采集数据')
    settings = load_settings()
    now = now or datetime.now(timezone.utc)
    at = parse_time(crawl_time)
    age = (now - at).total_seconds() / 3600
    if not 0 <= age <= MAX_AGE_HOURS or at.astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat() != day:
        raise ReportBlocked('发送检查未通过：数据过期、日期不符或时间异常')
    analysis = generate_full_analysis(crawl_time, settings)
    problems = []
    run = analysis['run']
    if run.get('status') != 'ok' or not run.get('finished_at') or run.get('error'):
        problems.append('采集未完整成功')
    charts = list(analysis['charts'].values())
    companies = analysis['companies']
    if not charts and not companies:
        problems.append('未启用任何监测项')
    bad_charts = missing_history = bad_rows = 0
    valid_links = set()
    signals = 0

    def add_product(app, platform, country):
        url = product_url(platform, app.get('app_id'), country)
        name = str(app.get('app_name') or '')
        if not url or not name.strip():
            return False
        # Existing report paths use 60/120-character labels.
        valid_links.update((url, name[:n]) for n in (60, 120))
        return True

    for chart in charts:
        scope, current = chart['scope'], chart['current']
        logs = query('''SELECT status,count FROM crawl_log WHERE crawl_time=? AND platform=?
            AND country=? AND chart_type=? ORDER BY id DESC LIMIT 1''',
            (crawl_time,scope['platform'],scope['country'],chart['db_chart_type']))
        if chart['status'] != 'ok' or not current or not logs or logs[0]['status'] != 'ok' or logs[0]['count'] != len(current):
            bad_charts += 1
            continue
        ranks = [a['rank'] for a in current]
        if ranks != list(range(1, len(current) + 1)) or len({a['app_id'] for a in current}) != len(current):
            bad_rows += 1
        if not all([add_product(a, scope['platform'], scope['country']) for a in current]):
            bad_rows += 1
        if not trial and not chart['previous_time']:
            missing_history += 1
        if chart['previous_time']:
            old = get_rankings_at(chart['previous_time'],scope['platform'],chart['db_chart_type'],scope['country'])
            if len(current) < min(settings['top_n'],len(old)) * 0.8:
                bad_rows += 1
        signals += sum(len(chart['changes'].get(k, [])) for k in ('surges','new_entries'))
    if bad_charts:
        problems.append(f'{bad_charts} 个榜单为空、缺失或采集异常')
    if missing_history:
        problems.append(f'{missing_history} 个榜单缺少有效对比历史')
    if bad_rows:
        problems.append('榜单排名、产品信息或采集深度异常')
    bad_catalogs = 0
    for data in companies:
        company = data['company']
        snaps = {s['country']: s for s in data['snapshots']}
        for country in company['countries']:
            snapshot = snaps.get(country)
            if not snapshot or snapshot['status'] != 'ok':
                bad_catalogs += 1
        for event in data['events']:
            if not add_product(event,company['platform'],event['country']):
                problems.append('公司新游缺少有效产品信息')
        signals += len(data['events'])
        if trial:
            for row in query('''SELECT country,data_json FROM publisher_apps
                WHERE platform=? AND developer_id=? AND last_seen=?''',
                (company['platform'],company['developer_id'],crawl_time)):
                if row['country'] in company['countries']:
                    add_product(json.loads(row['data_json']),company['platform'],row['country'])
    if bad_catalogs:
        problems.append(f'{bad_catalogs} 个公司账号目录未完整取得')
    if problems:
        raise ReportBlocked('发送检查未通过：' + '；'.join(dict.fromkeys(problems)))
    if not trial and not signals:
        raise ReportBlocked('本轮无符合条件的爬升、上榜或公司新增，不发送空日报')
    if not isinstance(parts, list) or not parts or any(not isinstance(p,str) or not p.strip() for p in parts):
        raise ReportBlocked('发送检查未通过：报告内容为空')
    from report import generate_report_parts
    from trial_review import generate_trial_review
    expected = generate_trial_review(crawl_time) if trial else generate_report_parts(crawl_time)
    if parts != expected:
        raise ReportBlocked('发送检查未通过：报告内容与采集结果不一致')
    parser = Links()
    parser.feed('\n'.join(parts))
    if not parser.links:
        raise ReportBlocked('发送检查未通过：卡片没有可展示的游戏')
    if any(link not in valid_links for link in parser.links):
        raise ReportBlocked('发送检查未通过：游戏名称与商店链接不匹配')
    from feishu_card import build_cards
    rendered = Links()
    for card in build_cards(parts,day,trial):
        for element in card['body']['elements']:
            if element.get('tag') == 'markdown':
                rendered.feed(element.get('content', ''))
    if Counter(rendered.links) != Counter(parser.links):
        raise ReportBlocked('发送检查未通过：卡片渲染丢失游戏名称或商店链接')
    return dict(version=VERSION,crawl_time=crawl_time,day=day,trial=trial,
                settings=monitor_settings(settings),parts=parts)


def seal_payload(approval, content):
    return json.dumps(dict(approval,content_hash=hashlib.sha256(content.encode()).hexdigest()),ensure_ascii=False)


def validate_saved_payload(row, day, trial=False):
    """Every retry must recheck its original payload; old unchecked rows are blocked."""
    try:
        approval = json.loads(row.get('approval_json') or '{}')
        valid = (approval.get('version') == VERSION and approval.get('day') == day
                 and approval.get('trial') == trial and row['msg_type'] == 'interactive'
                 and approval.get('content_hash') == hashlib.sha256(row['content'].encode()).hexdigest()
                 and approval.get('settings') == monitor_settings())
        if not valid:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise ReportBlocked('发送检查未通过：待发卡片缺少有效审核记录，或内容、配置已改变') from None
    validate_report(approval['parts'],day,trial,approval['crawl_time'])
    from feishu_card import build_cards
    cards = build_cards(approval['parts'],day,trial)
    if not 0 <= row['part'] < len(cards) or json.loads(row['content']) != cards[row['part']]:
        raise ReportBlocked('发送检查未通过：待发卡片与已核对的报告不一致')
