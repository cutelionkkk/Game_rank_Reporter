"""Compact daily digest; detailed analysis remains available in the export."""
from collections import defaultdict
from html import escape
from zoneinfo import ZoneInfo

from analyzer import generate_full_analysis
from config import load_settings
from database import parse_time
from genres import get_genre_display

PLATFORM_NAMES = {'gp': 'Google Play', 'ios': 'iOS'}
CHART_NAMES = {'free': '免费榜', 'paid': '付费榜', 'grossing': '畅销榜'}


def _text(value, limit=120):
    return escape(str(value or '')[:limit])


def _scope_label(scope):
    genre = '' if scope['genre'] == 'all' else get_genre_display(scope['genre'])
    return f"{scope['country'].upper()} · {genre}{CHART_NAMES.get(scope['chart_type'], scope['chart_type'])}"


def _sections(title, blocks, max_len):
    parts, current = [], title
    for block in blocks:
        if len(block) + len(title) + 4 > max_len:
            # Large company groups still respect the transport's message limit.
            for line in block.split('\n'):
                if len(current) + len(line) + 1 > max_len:
                    parts.append(current)
                    current = title + '（续）'
                current += '\n' + line
            continue
        if len(current) + len(block) + 2 > max_len and current != title:
            parts.append(current)
            current = title + '（续）'
        current += '\n\n' + block
    parts.append(current)
    return parts


def _rank_items(charts, kind):
    groups = {}
    for chart in charts:
        for app in chart['changes'].get(kind, []):
            key = (chart['scope']['platform'], app['app_id'])
            item = groups.setdefault(key, dict(app=app, platform=key[0], signals=[]))
            item['signals'].append((chart['scope'], app))
    score = (lambda x: -max(a['rank_change'] for _, a in x['signals'])) if kind == 'surges' else (
        lambda x: min(a['rank'] for _, a in x['signals']))
    return sorted(groups.values(), key=lambda x: (score(x), x['app']['app_name']))


def _rank_blocks(items, kind, limit):
    blocks = []
    for i, item in enumerate(items[:limit], 1):
        app = item['app']
        lines = [f"{i}. <b>{_text(app['app_name'])}</b> · {PLATFORM_NAMES[item['platform']]}"]
        if app.get('developer'):
            lines.append(_text(app['developer']))
        signals = sorted(item['signals'], key=lambda s: -s[1]['rank_change'] if kind == 'surges' else s[1]['rank'])
        for scope, a in signals[:3]:
            change = f"#{a['prev_rank']} → #{a['rank']}（↑{a['rank_change']}）" if kind == 'surges' else f"新进 #{a['rank']}"
            lines.append(_text(_scope_label(scope)) + '：' + change)
        if len(signals) > 3:
            lines.append(f"另有 {len(signals)-3} 个榜单信号")
        blocks.append('\n'.join(lines))
    if len(items) > limit:
        blocks.append(f'另有 {len(items)-limit} 款，本节仅展示前 {limit} 款。')
    return blocks


def generate_report_parts(crawl_time=None, max_len=3900):
    analysis = generate_full_analysis(crawl_time)
    if not analysis:
        return ['暂无监测数据，请先运行一次监测。']
    settings = load_settings()
    limit = settings['report_max_items']
    time = parse_time(analysis['crawl_time']).astimezone(ZoneInfo('Asia/Shanghai'))
    title = f'<b>游戏雷达 · {time:%m月%d日}</b>'
    window = f"对比约 {settings['comparison_hours']} 小时前" if settings['comparison_hours'] else '对比上次采集'
    blocks = [f"Top {settings['top_n']} · {window} · 上升 ≥{settings['rank_surge_threshold']} 名"]
    charts = list(analysis['charts'].values())
    comparable = [c for c in charts if c['status'] == 'ok' and c['previous_time']]
    chart_errors = [c for c in charts if c['status'] != 'ok']
    baselines = [c for c in charts if c['status'] == 'ok' and not c['previous_time']]
    if charts:
        surges = _rank_items(comparable, 'surges')
        entries = _rank_items(comparable, 'new_entries')
        for heading, items, kind in [('📈 快速爬升', surges, 'surges'), ('🆕 首次上榜', entries, 'new_entries')]:
            blocks.append('<b>' + heading + '</b>' + ('\n相较对比快照新上榜，不等于新发布。' if kind == 'new_entries' else ''))
            if items:
                blocks.extend(_rank_blocks(items, kind, limit))
            elif not comparable:
                blocks.append('暂缺可比数据，待后续日报比较。')
            else:
                blocks.append('可比榜单内暂无符合条件的游戏。')

    companies = analysis['companies']
    if companies:
        blocks.append('<b>🏢 关注公司新游</b>')
        groups = defaultdict(list)
        for data in companies:
            company = data['company']
            groups[company.get('group') or company['name']].append(data)
        for name, members in groups.items():
            events = {}
            incomplete, baseline = False, False
            for member in members:
                company = member['company']
                snaps = member['snapshots']
                incomplete |= len(snaps) < len(company['countries']) or any(s['status'] != 'ok' for s in snaps)
                baseline |= any(s.get('baseline') for s in snaps)
                for event in member['events']:
                    key = (company['platform'], event['app_id'])
                    item = events.setdefault(key, dict(event=event, company=company, countries=set()))
                    item['countries'].add(event['country'].upper())
            lines = ['<b>' + _text(name) + '</b>']
            ordered = sorted(events.values(), key=lambda x: (x['event']['kind'] != 'new_release', x['event']['app_name']))
            for item in ordered[:limit]:
                e, c = item['event'], item['company']
                label = '近期发布' if e['kind'] == 'new_release' else '首次发现，未确认为近期新游'
                if e['kind'] == 'new_release' and e.get('release_date'):
                    label += ' · ' + str(e['release_date'])[:10]
                lines.append(f"• {_text(e['app_name'])} · {PLATFORM_NAMES[c['platform']]} · {','.join(sorted(item['countries']))}")
                lines.append(f"  {_text(c['name'])}｜{_text(label)}")
            if len(ordered) > limit:
                lines.append(f'另有 {len(ordered)-limit} 款新增发现。')
            if not ordered:
                lines.append('部分账号数据未完整取得，暂不能确认有无新游。' if incomplete else
                             '新关注账号已建档，下次起识别新增。' if baseline else '暂无新增游戏。')
            elif incomplete or baseline:
                lines.append('部分账号仍在建档或数据不完整。')
            blocks.append('\n'.join(lines))

    notes = []
    if baselines:
        notes.append(f'{len(baselines)} 个榜单暂无可比历史。')
    shallow = [c for c in charts if c['status'] == 'ok' and len(c['current']) < settings['top_n']]
    if shallow:
        notes.append(f"{len(shallow)} 个榜单返回不足 Top {settings['top_n']}，按实际范围比较。")
    for c in chart_errors[:3]:
        notes.append(f"{PLATFORM_NAMES[c['scope']['platform']]} {_scope_label(c['scope'])}：{c.get('message') or '尚未采集'}")
    if len(chart_errors) > 3:
        notes.append(f'另有 {len(chart_errors)-3} 个榜单采集异常。')
    if notes:
        blocks.append('<b>采集说明</b>\n' + '\n'.join(_text(n,200) for n in notes))
    if not charts and not companies:
        return ['未启用监测项，请在本地网页中选择版块或公司。']
    return _sections(title, blocks, max_len)


def generate_report(crawl_time=None):
    return '\n\n'.join(generate_report_parts(crawl_time))


def generate_summary_line(crawl_time=None):
    a = generate_full_analysis(crawl_time)
    if not a:
        return '📊 游戏监测：暂无数据'
    surges = len(_rank_items(list(a['charts'].values()), 'surges'))
    events = sum(len(c['events']) for c in a['companies'])
    return f'📊 游戏监测：{surges} 款快速爬升游戏，{events} 个公司新增发现'


if __name__ == '__main__':
    print(generate_report())
