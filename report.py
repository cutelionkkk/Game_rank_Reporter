"""Report generator — one message per chart, focused on changes + insights"""

import json
from html import escape
from datetime import datetime
from collections import Counter, defaultdict

from analyzer import generate_full_analysis
from database import get_rankings_at, get_latest_crawl_time, get_all_chart_types_at
from config import load_settings
from genres import get_genre_display
from game_info import get_game_info

PLATFORM_NAMES = {'gp': 'Google Play', 'ios': 'iOS App Store'}
CHART_NAMES = {'free': '免费榜', 'paid': '付费榜', 'grossing': '畅销榜'}
CHART_EMOJI = {'free': '🆓', 'paid': '💵', 'grossing': '💰'}
PLATFORM_FLAG = {'ios': '🍎', 'gp': '🤖'}



def _parse_chart_key(key):
    parts = key.split('_', 1)
    platform = parts[0]
    rest = parts[1] if len(parts) > 1 else ''
    if ':' in rest:
        base_chart, genre = rest.split(':', 1)
    else:
        base_chart, genre = rest, 'all'
    return platform, base_chart, genre


def _chart_title(platform, base_chart, genre) -> str:
    flag = PLATFORM_FLAG.get(platform, '')
    pname = 'iOS' if platform == 'ios' else 'Google Play'
    cname = CHART_NAMES.get(base_chart, base_chart)
    if genre != 'all':
        gname = get_genre_display(genre)
        return f"{flag} {pname} {gname}{cname}"
    return f"{flag} {pname} {cname}"


def _fmt_change(change: int) -> str:
    if change > 0:
        return f"⬆️+{change}"
    elif change < 0:
        return f"⬇️{change}"
    return "→"


def _gameplay_tag(app: dict) -> str:
    info = get_game_info(
        app_name=app.get('app_name', ''),
        developer=app.get('developer', ''),
        app_id=app.get('app_id', ''),
        use_search=False,
    )
    gp = info.get('gameplay', '')
    return f"（{gp}）" if gp else ''


def _gameplay_label(app_name: str, developer: str = '', app_id: str = '') -> str:
    info = get_game_info(app_name=app_name, developer=developer,
                         app_id=app_id, use_search=False)
    return info.get('gameplay', '') or '其他'


def _developer_stats(apps: list, top_n: int = 5) -> list[str]:
    """统计开发商在榜产品数，返回格式化行列表"""
    dev_counter = Counter()
    dev_top_rank = {}   # 每个开发商的最高名次
    for a in apps:
        dev = (a.get('developer') or '').strip()
        if not dev:
            continue
        dev_counter[dev] += 1
        r = a.get('rank', 999)
        if dev not in dev_top_rank or r < dev_top_rank[dev]:
            dev_top_rank[dev] = r

    lines = []
    for dev, cnt in dev_counter.most_common(top_n):
        if cnt < 2:
            break  # 只列出多款在榜的
        top_r = dev_top_rank.get(dev, '?')
        lines.append(f"  {dev}：{cnt}款（最高 #{top_r}）")
    return lines


def _gameplay_distribution(apps: list, top_n: int = 10) -> list[str]:
    """统计玩法分类分布，返回格式化行列表"""
    gameplay_counter = Counter()
    for a in apps:
        tag = _gameplay_label(
            a.get('app_name', ''),
            a.get('developer', ''),
            a.get('app_id', ''),
        )
        gameplay_counter[tag] += 1

    lines = []
    for tag, cnt in gameplay_counter.most_common(top_n):
        bar = '█' * min(cnt // 3, 10)  # 简易条形图
        lines.append(f"  {tag}：{cnt}款 {bar}")
    return lines


def _text(value, limit=160):
    return escape(str(value or '')[:limit])


def _sections(title, lines, max_len):
    parts, current = [], title
    for line in lines:
        if len(current) + len(line) + 1 > max_len:
            parts.append(current)
            current = title + '（续）'
        current += '\n' + line
    parts.append(current)
    return parts


def generate_report_parts(crawl_time=None, max_len=3900):
    analysis = generate_full_analysis(crawl_time)
    if not analysis:
        return ['暂无监测数据，请先运行一次监测。']
    settings = load_settings()
    limit = settings['report_max_items']
    parts = []
    for chart in analysis['charts'].values():
        scope = chart['scope']
        title = '<b>' + _text(_chart_title(scope['platform'],scope['chart_type'],scope['genre']))
        title += f" · {scope['country'].upper()}</b>\n{_text(analysis['crawl_time'])}"
        lines = []
        if chart['status'] != 'ok':
            lines.append('⚠️ 本轮采集失败：' + _text(chart['message'],500) if chart['status'] == 'error' else '本轮尚未采集这个版块。')
        elif not chart['previous_time']:
            lines.append('📸 已记录快照；暂无符合对比窗口的历史数据，不判定排名爬升或新上榜。')
        else:
            lines.append(f"📈 <b>上升 ≥{chart['threshold']} 名</b> · 实际间隔 {chart['elapsed_hours']} 小时")
            lines.append('对比快照：' + _text(chart['previous_time']))
            changes = chart['changes']
            for a in changes['surges'][:limit]:
                lines.append(f"⬆ +{a['rank_change']} <b>{_text(a['app_name'])}</b> #{a['prev_rank']} → #{a['rank']} · {_text(a.get('developer'))}")
            if not changes['surges']:
                lines.append('本轮无达到阈值的上升项目。')
            if len(changes['surges']) > limit:
                lines.append(f"共 {len(changes['surges'])} 款达到阈值，完整结果见本地网页或 JSON 导出。")
            for a in changes['drops'][:limit]:
                lines.append(f"⬇ {a['rank_change']} {_text(a['app_name'])} #{a['prev_rank']} → #{a['rank']}")
            if changes['new_entries']:
                lines.append('🆕 新上榜（不等于新发布）：' + '、'.join(f"{_text(a['app_name'],60)} #{a['rank']}" for a in changes['new_entries'][:limit]))
            if changes['exits']:
                lines.append('离开可比榜单范围：' + '、'.join(_text(a['app_name'],60) for a in changes['exits'][:limit]))
        if chart['current']:
            lines.append(f"本轮取得 {len(chart['current'])} 款 · 目标 Top {settings['top_n']}")
            stats = _developer_stats(chart['current'])
            if stats:
                lines.append('🏢 <b>在榜产品数</b>')
                lines.extend(_text(line,250) for line in stats)
            gameplay = _gameplay_distribution(chart['current'], top_n=5)
            if gameplay:
                lines.append('🎮 <b>玩法分布（规则/缓存标签）</b>')
                lines.extend(_text(line,250) for line in gameplay)
        parts.extend(_sections(title,lines,max_len))
    for data in analysis['companies']:
        company = data['company']
        title = f"🏢 <b>{_text(company['name'])} · {PLATFORM_NAMES[company['platform']]}</b>\n{_text(analysis['crawl_time'])}"
        lines = []
        for snap in data['snapshots']:
            country = snap['country'].upper()
            if snap['status'] == 'error':
                lines.append(f"⚠️ {country} 采集失败：{_text(snap['message'],500)}")
            else:
                lines.append(f"{country}：取得 {snap['count']} 款游戏" + ('，首次建立基线' if snap['baseline'] else ''))
                if snap['message']:
                    lines.append('⚠️ ' + _text(snap['message'],300))
        for event in data['events'][:limit]:
            label = '近期发布' if event['kind'] == 'new_release' else '首次发现（不确定为新游）'
            lines.append(f"🆕 <b>{_text(event['app_name'])}</b> · {label} · {event['country'].upper()}")
            lines.append('商店首发日期：' + _text(event.get('release_date') or '未知') + '；首次监测：' + _text(event['first_seen']))
        if len(data['events']) > limit:
            lines.append(f"共发现 {len(data['events'])} 款，完整结果见本地网页。")
        elif not data['events']:
            lines.append('本轮无新增发现。' if data['snapshots'] and all(s['status'] != 'error' for s in data['snapshots']) else '本轮数据不足，无法判断新增。')
        parts.extend(_sections(title,lines,max_len))
    return parts or ['未启用监测项，请在本地网页中选择版块或公司。']


def generate_report(crawl_time=None):
    return ('\n\n' + '─' * 40 + '\n\n').join(generate_report_parts(crawl_time))


def generate_summary_line(crawl_time=None):
    a = generate_full_analysis(crawl_time)
    if not a:
        return '📊 游戏监测：暂无数据'
    surges = sum(len(c['changes'].get('surges',[])) for c in a['charts'].values())
    events = sum(len(c['events']) for c in a['companies'])
    return f'📊 游戏监测：{surges} 个榜单爬升信号，{events} 个公司新增发现'


if __name__ == '__main__':
    print(generate_report())
