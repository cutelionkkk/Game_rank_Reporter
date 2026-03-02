"""Report generator — one message per chart, focused on changes + insights"""

import json
from datetime import datetime
from collections import Counter, defaultdict

from analyzer import generate_full_analysis
from database import get_rankings_at, get_latest_crawl_time, get_all_chart_types_at
from config import REPORT_MAX_ITEMS
from genres import get_genre_display
from game_info import get_game_info

PLATFORM_NAMES = {'gp': 'Google Play', 'ios': 'iOS App Store'}
CHART_NAMES = {'free': '免费榜', 'paid': '付费榜', 'grossing': '畅销榜'}
CHART_EMOJI = {'free': '🆓', 'paid': '💵', 'grossing': '💰'}
PLATFORM_FLAG = {'ios': '🍎', 'gp': '🤖'}

# 名次变动阈值：绝对值超过此值才列出
RANK_CHANGE_THRESHOLD = 10


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


def _generate_chart_message(
    platform: str,
    base_chart: str,
    genre: str,
    crawl_time: str,
    chart_data: dict,
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
    lines.append(f"{emoji} <b>{title}</b> — {time_str}\n")

    changes = chart_data.get('changes', {})
    has_history = bool(chart_data.get('previous_time'))

    # ── 1. 名次变动（仅列出变动 ≥ RANK_CHANGE_THRESHOLD 的） ──
    if not has_history:
        lines.append('📸 <i>首次快照，下次抓取后显示变动分析</i>')
    else:
        prev_apps = get_rankings_at(chart_data['previous_time'], platform, db_chart_type)
        prev_map = {a['app_id']: a['rank'] for a in prev_apps}

        # 计算所有 app 的变动，过滤绝对值 >= 阈值
        movers_up = []    # 上升 >= 阈值
        movers_down = []  # 下降 >= 阈值
        new_entries = []  # 新上榜

        for app in apps:
            aid = app['app_id']
            curr_rank = app['rank']
            if aid not in prev_map:
                new_entries.append(app)
            else:
                diff = prev_map[aid] - curr_rank  # 正=上升
                if diff >= RANK_CHANGE_THRESHOLD:
                    movers_up.append({**app, 'prev_rank': prev_map[aid], 'rank_change': diff})
                elif diff <= -RANK_CHANGE_THRESHOLD:
                    movers_down.append({**app, 'prev_rank': prev_map[aid], 'rank_change': diff})

        exits = [a for a in prev_apps if a['app_id'] not in {x['app_id'] for x in apps}]

        movers_up.sort(key=lambda x: x['rank_change'], reverse=True)
        movers_down.sort(key=lambda x: x['rank_change'])
        new_entries.sort(key=lambda x: x['rank'])

        lines.append('📈 <b>名次变动（±10以上）</b>')

        if movers_up:
            for a in movers_up[:6]:
                gp = _gameplay_tag(a)
                lines.append(
                    f"  ⬆️ <b>+{a['rank_change']}</b> {a['app_name']}{gp} "
                    f"#{a['prev_rank']}→#{a['rank']}"
                )
        else:
            lines.append('  （无大幅上升）')

        if movers_down:
            for a in movers_down[:6]:
                gp = _gameplay_tag(a)
                lines.append(
                    f"  ⬇️ <b>{a['rank_change']}</b> {a['app_name']}{gp} "
                    f"#{a['prev_rank']}→#{a['rank']}"
                )

        if new_entries:
            new_strs = [f"{a['app_name']}(#{a['rank']})" for a in new_entries[:4]]
            suffix = f'等共{len(new_entries)}款' if len(new_entries) > 4 else ''
            lines.append(f"  🆕 新上榜: {', '.join(new_strs)}{suffix}")

        if exits:
            exit_strs = [a['app_name'] for a in exits[:3]]
            suffix = f' 等{len(exits)}款' if len(exits) > 3 else ''
            lines.append(f"  🚪 跌出: {', '.join(exit_strs)}{suffix}")

        if not movers_up and not movers_down and not new_entries:
            lines.append('  本轮榜单稳定，无显著变动')

    lines.append('')

    # ── 2. 厂商排名（多款在榜） ──
    dev_lines = _developer_stats(apps, top_n=5)
    if dev_lines:
        lines.append('🏢 <b>在榜产品数（厂商）</b>')
        lines.extend(dev_lines)
        lines.append('')

    # ── 3. 玩法分类分布（Top 10） ──
    gameplay_lines = _gameplay_distribution(apps, top_n=10)
    if gameplay_lines:
        lines.append('🎮 <b>玩法分类（Top 100）</b>')
        lines.extend(gameplay_lines)

    msg = '\n'.join(lines)
    if len(msg) > max_len:
        msg = msg[:max_len - 30] + '\n…（内容已截断）'
    return msg


def generate_report_parts(crawl_time=None, max_len=3900) -> list[str]:
    """Generate one message per chart."""
    analysis = generate_full_analysis(crawl_time)
    if not analysis:
        return ['❌ 没有数据可分析，请先运行爬虫。']

    ct = analysis['crawl_time']
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
            max_len=max_len,
        )
        if msg:
            parts.append(msg)

    return parts or ['⚠️ 榜单数据为空，请检查爬虫是否正常运行。']


def generate_report(crawl_time=None) -> str:
    """Combine all chart messages into one string (for file save / legacy)."""
    parts = generate_report_parts(crawl_time)
    sep = '\n\n' + '─' * 40 + '\n\n'
    return sep.join(parts)


def generate_summary_line(crawl_time=None) -> str:
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
    import re
    for i, p in enumerate(parts):
        clean = re.sub(r'<[^>]+>', '', p)
        print(f'\n{"="*50}\nPART {i+1} ({len(p)} chars)\n{"="*50}')
        print(clean)
