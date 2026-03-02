"""Report generator — one message per chart, with gameplay analysis"""

import json
from datetime import datetime
from collections import Counter

from analyzer import generate_full_analysis
from database import get_rankings_at, get_latest_crawl_time, get_all_chart_types_at
from config import REPORT_MAX_ITEMS
from genres import get_genre_display
from game_info import get_game_info

PLATFORM_NAMES = {'gp': 'Google Play', 'ios': 'iOS App Store'}
CHART_NAMES = {'free': '免费榜', 'paid': '付费榜', 'grossing': '畅销榜'}
CHART_EMOJI = {'free': '🆓', 'paid': '💵', 'grossing': '💰'}
PLATFORM_FLAG = {'ios': '🍎', 'gp': '🤖'}


def _parse_chart_key(key):
    """'ios_free:casual' → (ios, free, casual)"""
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
    """Return gameplay string like '(三消益智)' or '' if unknown"""
    info = get_game_info(
        app_name=app.get('app_name', ''),
        developer=app.get('developer', ''),
        app_id=app.get('app_id', ''),
        use_search=False,   # 报告生成时不实时搜索，依赖缓存+规则
    )
    gp = info.get('gameplay', '')
    return f"（{gp}）" if gp else ''


def _generate_chart_message(
    platform: str,
    base_chart: str,
    genre: str,
    crawl_time: str,
    chart_data: dict,
    top_n: int = 10,
    max_len: int = 3900,
) -> str:
    """Build one message for a single chart."""
    db_chart_type = base_chart if genre == 'all' else f"{base_chart}:{genre}"
    apps = get_rankings_at(crawl_time, platform, db_chart_type)
    if not apps:
        return ''

    title = _chart_title(platform, base_chart, genre)
    emoji = CHART_EMOJI.get(base_chart, '📊')

    try:
        dt = datetime.fromisoformat(crawl_time.replace('Z', '+00:00'))
        time_str = dt.strftime('%Y-%m-%d %H:%M UTC')
    except Exception:
        time_str = crawl_time

    lines = []
    lines.append(f"{emoji} <b>{title} Top {top_n}</b> — {time_str}\n")

    # ── Top N games ──────────────────────────────────────────
    changes = chart_data.get('changes', {})
    prev_map = {}
    if chart_data.get('previous_time'):
        prev_apps = get_rankings_at(chart_data['previous_time'], platform, db_chart_type)
        prev_map = {a['app_id']: a['rank'] for a in prev_apps}

    for app in apps[:top_n]:
        rank = app['rank']
        name = app['app_name']
        dev = app.get('developer') or ''
        gameplay = _gameplay_tag(app)

        # Rank change indicator
        if prev_map:
            prev_rank = prev_map.get(app['app_id'])
            if prev_rank is None:
                change_tag = ' 🆕'
            else:
                diff = prev_rank - rank
                change_tag = f' {_fmt_change(diff)}' if diff != 0 else ''
        else:
            change_tag = ''

        line = f"<b>#{rank}</b> {name}{gameplay}{change_tag}"
        if dev:
            line += f"\n    <i>{dev}</i>"
        lines.append(line)

    # ── Changes summary ──────────────────────────────────────
    lines.append('')
    has_history = bool(chart_data.get('previous_time'))

    if not has_history:
        lines.append('📸 首次快照，下次抓取后显示变动分析')
    else:
        surges = changes.get('surges', [])
        drops = changes.get('drops', [])
        new_entries = changes.get('new_entries', [])
        exits = changes.get('exits', [])

        summary_parts = []
        if surges:
            top_surge = surges[0]
            gp = _gameplay_tag(top_surge)
            summary_parts.append(
                f"🔥 飙升: {top_surge['app_name']}{gp} "
                f"#{top_surge['prev_rank']}→#{top_surge['rank']}"
                + (f"（共{len(surges)}款↑）" if len(surges) > 1 else '')
            )
        if drops:
            top_drop = drops[0]
            gp = _gameplay_tag(top_drop)
            summary_parts.append(
                f"📉 下跌: {top_drop['app_name']}{gp} "
                f"#{top_drop['prev_rank']}→#{top_drop['rank']}"
                + (f"（共{len(drops)}款↓）" if len(drops) > 1 else '')
            )
        if new_entries:
            new_names = [f"{a['app_name']}(#{a['rank']})" for a in new_entries[:3]]
            extra = f"等{len(new_entries)}款" if len(new_entries) > 3 else f"{len(new_entries)}款"
            summary_parts.append(f"🆕 新上榜: {', '.join(new_names)}" +
                                  (f"等{len(new_entries)-3}款更多" if len(new_entries) > 3 else ''))
        if exits:
            exit_names = [a['app_name'] for a in exits[:2]]
            summary_parts.append(f"🚪 跌出: {', '.join(exit_names)}" +
                                  (f" 等{len(exits)}款" if len(exits) > 2 else ''))

        if summary_parts:
            lines.append('📊 本轮变动：')
            for p in summary_parts:
                lines.append(f"  {p}")
        else:
            lines.append('📊 本轮榜单稳定，无显著变动')

    msg = '\n'.join(lines)

    # Hard trim if somehow exceeds limit
    if len(msg) > max_len:
        msg = msg[:max_len - 30] + '\n…（内容已截断）'

    return msg


def generate_report_parts(crawl_time=None, top_n=None, max_len=3900) -> list[str]:
    """
    Generate one message per chart.
    Returns list[str] — each item is sent as a separate Telegram/Discord message.
    """
    analysis = generate_full_analysis(crawl_time)
    if not analysis:
        return ['❌ 没有数据可分析，请先运行爬虫。']

    ct = analysis['crawl_time']
    effective_top_n = top_n or REPORT_MAX_ITEMS

    parts = []
    for key in sorted(analysis['charts'].keys()):
        platform, base_chart, genre = _parse_chart_key(key)
        chart_data = analysis['charts'][key]
        msg = _generate_chart_message(
            platform=platform,
            base_chart=base_chart,
            genre=genre,
            crawl_time=ct,
            chart_data=chart_data,
            top_n=effective_top_n,
            max_len=max_len,
        )
        if msg:
            parts.append(msg)

    if not parts:
        return ['⚠️ 榜单数据为空，请检查爬虫是否正常运行。']

    return parts


def generate_report(crawl_time=None) -> str:
    """Combine all chart messages into one string (for file save / legacy)."""
    parts = generate_report_parts(crawl_time)
    sep = '\n\n' + '─' * 40 + '\n\n'
    return sep.join(parts)


def generate_summary_line(crawl_time=None) -> str:
    """One-line summary for heartbeat checks"""
    analysis = generate_full_analysis(crawl_time)
    if not analysis:
        return '📊 游戏榜单：暂无数据'

    total_surges = total_drops = total_new = 0
    for key, data in analysis['charts'].items():
        ch = data.get('changes', {})
        total_surges += len(ch.get('surges', []))
        total_drops += len(ch.get('drops', []))
        total_new += len(ch.get('new_entries', []))

    return f'📊 游戏榜单：{total_surges}飙升 {total_drops}暴跌 {total_new}新上榜'


if __name__ == '__main__':
    parts = generate_report_parts()
    print(f'Total parts: {len(parts)}')
    for i, p in enumerate(parts):
        print(f'\n{"="*50}\nPART {i+1} ({len(p)} chars)\n{"="*50}')
        print(p)
