"""Report generator — focused on analysis, not listing"""

import json
from datetime import datetime
from collections import defaultdict, Counter

from analyzer import generate_full_analysis
from database import get_rankings_at, get_latest_crawl_time, get_all_crawl_times, get_db
from config import REPORT_MAX_ITEMS
from genres import GENRES, CHART_TYPES, get_genre_display


PLATFORM_NAMES = {'gp': 'Google Play', 'ios': 'iOS App Store'}
CHART_NAMES = {'free': '免费榜', 'paid': '付费榜', 'grossing': '畅销榜'}
CHART_EMOJI = {'free': '🆓', 'paid': '💵', 'grossing': '💰'}


def _parse_chart_key(key):
    """Parse 'ios_free' or 'ios_free:casual' into (platform, base_chart, genre)"""
    parts = key.split('_', 1)
    platform = parts[0]
    rest = parts[1] if len(parts) > 1 else ''
    if ':' in rest:
        base_chart, genre = rest.split(':', 1)
    else:
        base_chart = rest
        genre = 'all'
    return platform, base_chart, genre


def _chart_display(platform, base_chart, genre):
    """Human-readable chart name like 'iOS 休闲免费榜'"""
    pname = "iOS" if platform == 'ios' else "GP"
    cname = CHART_NAMES.get(base_chart, base_chart)
    if genre != 'all':
        gname = get_genre_display(genre)
        return f"{pname} {gname}{cname}"
    return f"{pname} {cname}"


def fmt_change(change):
    if change > 0:
        return f"⬆️+{change}"
    elif change < 0:
        return f"⬇️{change}"
    return "→"


def _get_category_distribution(crawl_time, platform, chart_type):
    """Get category counts for a specific crawl"""
    apps = get_rankings_at(crawl_time, platform, chart_type)
    counter = Counter()
    for a in apps:
        cat = a.get('category') or ''
        if cat:
            counter[cat] += 1
    return counter, len(apps)


def _generate_first_crawl_report(analysis):
    """首次抓取：做快照分析而不是列名单"""
    lines = []
    lines.append("📸 **首次抓取快照**")
    lines.append("*尚无历史对比数据，以下为当前市场格局概览。下次抓取后将生成完整变动分析。*")
    lines.append("")

    ct = analysis['crawl_time']

    # Group charts by platform
    from collections import OrderedDict
    by_platform = OrderedDict()
    for key in sorted(analysis['charts'].keys()):
        platform, base_chart, genre = _parse_chart_key(key)
        by_platform.setdefault(platform, []).append((key, base_chart, genre))

    for platform, chart_entries in by_platform.items():
        pname = PLATFORM_NAMES.get(platform, platform)
        lines.append(f"**{pname}**")

        for key, base_chart, genre in chart_entries:
            db_chart_type = base_chart if genre == 'all' else f"{base_chart}:{genre}"
            apps = get_rankings_at(ct, platform, db_chart_type)
            if not apps:
                continue

            label = _chart_display(platform, base_chart, genre)
            emoji = CHART_EMOJI.get(base_chart, '📊')

            cat_counter = Counter()
            devs = Counter()
            for a in apps:
                cat = a.get('category') or ''
                dev = a.get('developer') or ''
                if cat:
                    cat_counter[cat] += 1
                if dev:
                    devs[dev] += 1

            lines.append(f"{emoji} {label} ({len(apps)}款)")

            top3 = [a['app_name'] for a in apps[:3]]
            lines.append(f"  🏆 Top 3: {' / '.join(top3)}")

            if cat_counter and genre == 'all':
                top_cats = cat_counter.most_common(5)
                cat_str = " | ".join(f"{c}: {n}款" for c, n in top_cats)
                lines.append(f"  📂 品类: {cat_str}")

            multi_devs = [(d, n) for d, n in devs.most_common(5) if n >= 2]
            if multi_devs:
                dev_str = ", ".join(f"{d}({n}款)" for d, n in multi_devs)
                lines.append(f"  🏢 多款在榜: {dev_str}")

        lines.append("")

    return "\n".join(lines)


def _generate_change_report(analysis):
    """有对比数据时：专注分析变动趋势"""
    lines = []

    # ========== 全局概览 ==========
    total_surges = 0
    total_drops = 0
    total_new = 0
    total_exits = 0
    all_surges = []
    all_drops = []
    all_new_entries = []

    for key, data in analysis['charts'].items():
        platform, base_chart, genre = _parse_chart_key(key)
        chart_label = _chart_display(platform, base_chart, genre)
        changes = data.get('changes', {})
        surges = changes.get('surges', [])
        drops = changes.get('drops', [])
        new_entries = changes.get('new_entries', [])
        exits = changes.get('exits', [])

        total_surges += len(surges)
        total_drops += len(drops)
        total_new += len(new_entries)
        total_exits += len(exits)

        for s in surges:
            all_surges.append({**s, '_label': chart_label})
        for d in drops:
            all_drops.append({**d, '_label': chart_label})
        for n in new_entries:
            all_new_entries.append({**n, '_label': chart_label})

    # 概览
    lines.append(f"📈 飙升 {total_surges} | 📉 暴跌 {total_drops} | 🆕 新上榜 {total_new} | 🚪 跌出 {total_exits}")
    lines.append("")

    # ========== 1. 排名飙升最快 (跨榜单) ==========
    all_surges.sort(key=lambda x: x['rank_change'], reverse=True)
    if all_surges:
        lines.append("**🔥 飙升最快**")
        for s in all_surges[:8]:
            cat = s.get('category') or ''
            cat_tag = f" [{cat}]" if cat else ""
            lines.append(
                f"  {fmt_change(s['rank_change'])} **{s['app_name']}**{cat_tag} "
                f"#{s['prev_rank']}→#{s['rank']} ({s['_label']})"
            )
        lines.append("")

    # ========== 2. 排名暴跌 (跨榜单) ==========
    all_drops.sort(key=lambda x: x['rank_change'])
    if all_drops:
        lines.append("**📉 下跌最快**")
        for d in all_drops[:6]:
            cat = d.get('category') or ''
            cat_tag = f" [{cat}]" if cat else ""
            lines.append(
                f"  {fmt_change(d['rank_change'])} **{d['app_name']}**{cat_tag} "
                f"#{d['prev_rank']}→#{d['rank']} ({d['_label']})"
            )
        lines.append("")

    # ========== 3. 新上榜亮点 ==========
    all_new_entries.sort(key=lambda x: x['rank'])
    if all_new_entries:
        lines.append("**🆕 新上榜亮点**")
        shown = 0
        for n in all_new_entries:
            if shown >= 6:
                break
            cat = n.get('category') or ''
            cat_tag = f" [{cat}]" if cat else ""
            new_tag = " 🌟新游戏" if n.get('is_new_game') else ""
            lines.append(
                f"  #{n['rank']} **{n['app_name']}**{cat_tag}{new_tag} ({n['_label']})"
            )
            shown += 1
        remaining = len(all_new_entries) - shown
        if remaining > 0:
            lines.append(f"  ...及其他 {remaining} 款")
        lines.append("")

    # ========== 4. 品类变化分析 ==========
    cat_analysis_lines = []
    for key, trends in analysis.get('category_trends', {}).items():
        if not trends:
            continue
        platform, base_chart, genre = _parse_chart_key(key)
        if genre != 'all':
            continue  # 子品类榜单不需要品类趋势分析
        label = _chart_display(platform, base_chart, genre)
        rising = [t for t in trends if t['change'] > 0]
        falling = [t for t in trends if t['change'] < 0]

        for t in rising[:3]:
            cat_analysis_lines.append(
                f"  📈 **{t['category']}** +{t['change']}款 "
                f"({t['previous_count']}→{t['current_count']}) — {label}"
            )
        for t in falling[:2]:
            cat_analysis_lines.append(
                f"  📉 **{t['category']}** {t['change']}款 "
                f"({t['previous_count']}→{t['current_count']}) — {label}"
            )

    if cat_analysis_lines:
        lines.append("**📊 品类趋势变化**")
        lines.extend(cat_analysis_lines[:8])
        lines.append("")

    # ========== 5. 各榜单品类分布 (仅 "all" 品类榜单) ==========
    ct = analysis['crawl_time']
    dist_lines = []
    for key in analysis['charts']:
        platform, base_chart, genre = _parse_chart_key(key)
        if genre != 'all':
            continue
        if base_chart not in ('grossing', 'free'):
            continue
        cat_counter, total = _get_category_distribution(ct, platform, base_chart)
        if not cat_counter or total < 10:
            continue
        label = _chart_display(platform, base_chart, genre)
        top5 = cat_counter.most_common(5)
        parts = []
        for cat, count in top5:
            pct = round(count / total * 100)
            parts.append(f"{cat} {count}款({pct}%)")
        dist_lines.append(f"  {label}: {' | '.join(parts)}")

    if dist_lines:
        lines.append("**📂 Top 100 品类分布**")
        lines.extend(dist_lines)
        lines.append("")

    # ========== 6. 持续上升 ==========
    riser_lines = []
    for key, risers in analysis.get('consecutive_risers', {}).items():
        platform, base_chart, genre = _parse_chart_key(key)
        label = _chart_display(platform, base_chart, genre)
        for r in risers[:3]:
            riser_lines.append(
                f"  **{r['app_name']}** #{r['first_rank']}→#{r['current_rank']} "
                f"连续{r['consecutive_rises']}次↑ ({label})"
            )

    if riser_lines:
        lines.append("**🚀 持续上升（连续多次排名提升）**")
        lines.extend(riser_lines[:6])
        lines.append("")

    # ========== 7. 头部开发商动态 ==========
    dev_lines = _analyze_developers(ct)
    if dev_lines:
        lines.append("**🏢 开发商动态**")
        lines.extend(dev_lines)
        lines.append("")

    # 如果什么变动都没有
    if total_surges == 0 and total_drops == 0 and total_new == 0:
        lines.append("💤 本轮榜单相对稳定，无显著排名变动。")
        lines.append("")

    return "\n".join(lines)


def _analyze_developers(crawl_time):
    """分析开发商：谁有多款产品在头部"""
    dev_apps = defaultdict(list)

    for platform in ['ios', 'gp']:
        for chart_type in ['grossing']:  # 主要看畅销榜
            apps = get_rankings_at(crawl_time, platform, chart_type)
            pname = "iOS" if platform == 'ios' else "GP"
            for a in apps[:50]:  # Top 50
                dev = a.get('developer') or ''
                if dev:
                    dev_apps[dev].append({
                        'name': a['app_name'],
                        'rank': a['rank'],
                        'platform': pname,
                    })

    lines = []
    # 按产品数量排序
    multi = [(dev, apps) for dev, apps in dev_apps.items() if len(apps) >= 2]
    multi.sort(key=lambda x: len(x[1]), reverse=True)

    for dev, apps in multi[:5]:
        app_strs = [f"{a['name']}(#{a['rank']} {a['platform']})" for a in apps[:4]]
        lines.append(f"  **{dev}** — {len(apps)}款: {', '.join(app_strs)}")

    return lines


def generate_report(crawl_time=None):
    """Generate analysis-focused report"""
    analysis = generate_full_analysis(crawl_time)
    if not analysis:
        return "❌ 没有数据可分析。请先运行爬虫。"

    ct = analysis['crawl_time']
    try:
        dt = datetime.fromisoformat(ct.replace('Z', '+00:00'))
        time_str = dt.strftime("%Y-%m-%d %H:%M UTC")
    except:
        time_str = ct

    header = []
    header.append(f"📊 **游戏榜单分析报告** — {time_str}")
    header.append(f"🇺🇸 美国区 | Top 100 | iOS + Google Play")
    header.append("")

    # 判断是否有历史对比数据
    has_comparison = False
    for key, data in analysis['charts'].items():
        if data.get('previous_time'):
            changes = data.get('changes', {})
            # 有对比数据 = 有非 new_entry 的变化 或 new_entry 不是全部
            surges = changes.get('surges', [])
            drops = changes.get('drops', [])
            up = changes.get('top_movers_up', [])
            down = changes.get('top_movers_down', [])
            if surges or drops or up or down:
                has_comparison = True
                break

    if has_comparison:
        body = _generate_change_report(analysis)
    else:
        body = _generate_first_crawl_report(analysis)

    report = "\n".join(header) + body

    # Discord 2000 字符限制 → 分段发送时用 generate_report_parts
    if len(report) > 1950:
        report = report[:1950] + "\n\n_(报告较长，完整版见 latest_report.txt)_"

    return report


def generate_report_parts(crawl_time=None, max_len=1900):
    """Generate report split into multiple parts for Discord"""
    analysis = generate_full_analysis(crawl_time)
    if not analysis:
        return ["❌ 没有数据可分析。请先运行爬虫。"]

    ct = analysis['crawl_time']
    try:
        dt = datetime.fromisoformat(ct.replace('Z', '+00:00'))
        time_str = dt.strftime("%Y-%m-%d %H:%M UTC")
    except:
        time_str = ct

    header = f"📊 **游戏榜单分析报告** — {time_str}\n🇺🇸 美国区 | Top 100 | iOS + Google Play\n\n"

    has_comparison = False
    for key, data in analysis['charts'].items():
        if data.get('previous_time'):
            changes = data.get('changes', {})
            if changes.get('surges') or changes.get('drops') or \
               changes.get('top_movers_up') or changes.get('top_movers_down'):
                has_comparison = True
                break

    if has_comparison:
        body = _generate_change_report(analysis)
    else:
        body = _generate_first_crawl_report(analysis)

    full = header + body

    # Split into parts
    if len(full) <= max_len:
        return [full]

    parts = []
    current = ""
    for line in full.split("\n"):
        if len(current) + len(line) + 1 > max_len:
            parts.append(current.rstrip())
            current = line + "\n"
        else:
            current += line + "\n"
    if current.strip():
        parts.append(current.rstrip())

    return parts


def generate_summary_line(crawl_time=None):
    """Generate a one-line summary for heartbeat checks"""
    analysis = generate_full_analysis(crawl_time)
    if not analysis:
        return "📊 游戏榜单：暂无数据"

    total_surges = 0
    total_new = 0
    total_drops = 0
    for key, data in analysis['charts'].items():
        changes = data.get('changes', {})
        total_surges += len(changes.get('surges', []))
        total_new += len(changes.get('new_entries', []))
        total_drops += len(changes.get('drops', []))

    return f"📊 游戏榜单：{total_surges}飙升 {total_drops}暴跌 {total_new}新上榜"


if __name__ == "__main__":
    print(generate_report())
