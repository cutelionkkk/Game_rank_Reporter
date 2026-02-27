"""Report generator for Discord output"""

from datetime import datetime
from analyzer import generate_full_analysis
from config import REPORT_MAX_ITEMS


PLATFORM_NAMES = {'gp': 'Google Play', 'ios': 'iOS App Store'}
CHART_NAMES = {'free': '免费榜', 'paid': '付费榜', 'grossing': '畅销榜'}
CHART_EMOJI = {'free': '🆓', 'paid': '💵', 'grossing': '💰'}


def format_rank_change(change):
    """Format rank change with arrow"""
    if change > 0:
        return f"⬆️+{change}"
    elif change < 0:
        return f"⬇️{change}"
    return "➡️"


def generate_report(crawl_time=None):
    """Generate a Discord-friendly report"""
    analysis = generate_full_analysis(crawl_time)
    if not analysis:
        return "❌ 没有数据可分析。请先运行爬虫。"

    ct = analysis['crawl_time']
    try:
        dt = datetime.fromisoformat(ct.replace('Z', '+00:00'))
        time_str = dt.strftime("%Y-%m-%d %H:%M UTC")
    except:
        time_str = ct

    lines = []
    lines.append(f"📊 **游戏榜单分析报告** — {time_str}")
    lines.append(f"🇺🇸 美国区 | Top 100")
    lines.append("")

    has_content = False

    for platform in ['ios', 'gp']:
        platform_name = PLATFORM_NAMES[platform]
        platform_sections = []

        for chart_type in ['free', 'paid', 'grossing']:
            key = f"{platform}_{chart_type}"
            data = analysis['charts'].get(key, {})
            changes = data.get('changes', {})
            prev_time = data.get('previous_time')

            emoji = CHART_EMOJI[chart_type]
            chart_name = CHART_NAMES[chart_type]

            section_lines = []

            # --- 飙升 ---
            surges = changes.get('surges', [])[:REPORT_MAX_ITEMS]
            if surges:
                section_lines.append(f"**🔥 飙升最快**")
                for i, app in enumerate(surges, 1):
                    section_lines.append(
                        f"  {i}. {format_rank_change(app['rank_change'])} "
                        f"**{app['app_name']}** — {app.get('category', '?')} — "
                        f"#{app['prev_rank']}→#{app['rank']}"
                    )

            # --- 新上榜 ---
            new_entries = changes.get('new_entries', [])[:REPORT_MAX_ITEMS]
            if new_entries:
                section_lines.append(f"**🆕 新上榜**")
                for i, app in enumerate(new_entries, 1):
                    new_tag = " 🌟新游戏" if app.get('is_new_game') else ""
                    section_lines.append(
                        f"  {i}. #{app['rank']} **{app['app_name']}** — "
                        f"{app.get('category', '?')}{new_tag}"
                    )

            # --- 暴跌 ---
            drops = changes.get('drops', [])[:5]
            if drops:
                section_lines.append(f"**📉 大幅下跌**")
                for i, app in enumerate(drops, 1):
                    section_lines.append(
                        f"  {i}. {format_rank_change(app['rank_change'])} "
                        f"**{app['app_name']}** — #{app['prev_rank']}→#{app['rank']}"
                    )

            # --- 跌出榜单 ---
            exits = changes.get('exits', [])[:5]
            if exits:
                section_lines.append(f"**🚪 跌出 Top 100**")
                for app in exits:
                    section_lines.append(f"  - {app['app_name']} (原#{app['rank']})")

            if section_lines:
                platform_sections.append((chart_type, section_lines))

        # --- 品类趋势 ---
        cat_lines = []
        for chart_type in ['free', 'grossing']:
            key = f"{platform}_{chart_type}"
            trends = analysis.get('category_trends', {}).get(key, [])
            rising = [t for t in trends if t['change'] > 0][:5]
            if rising:
                chart_name = CHART_NAMES[chart_type]
                for t in rising:
                    cat_lines.append(
                        f"  - **{t['category']}** {chart_name}: "
                        f"{t['previous_count']}→{t['current_count']}款 (+{t['change']})"
                    )

        # --- 持续上升 ---
        riser_lines = []
        for chart_type in ['free', 'grossing']:
            key = f"{platform}_{chart_type}"
            risers = analysis.get('consecutive_risers', {}).get(key, [])[:5]
            if risers:
                chart_name = CHART_NAMES[chart_type]
                for r in risers:
                    riser_lines.append(
                        f"  - **{r['app_name']}** ({chart_name}) — "
                        f"#{r['first_rank']}→#{r['current_rank']} "
                        f"(连续{r['consecutive_rises']}次上升)"
                    )

        # Output platform section
        if platform_sections or cat_lines or riser_lines:
            has_content = True
            lines.append(f"{'─' * 30}")
            lines.append(f"**{platform_name}**")
            lines.append("")

            for chart_type, section_lines in platform_sections:
                emoji = CHART_EMOJI[chart_type]
                chart_name = CHART_NAMES[chart_type]
                lines.append(f"{emoji} **{chart_name}**")
                lines.extend(section_lines)
                lines.append("")

            if cat_lines:
                lines.append("**📈 品类趋势（7日）**")
                lines.extend(cat_lines)
                lines.append("")

            if riser_lines:
                lines.append("**🚀 持续上升**")
                lines.extend(riser_lines)
                lines.append("")

    if not has_content:
        # First crawl, no comparison data
        lines.append("ℹ️ 首次抓取，暂无对比数据。下次抓取后会生成完整的变动分析。")
        lines.append("")

        # Show current top 5 for each chart
        for platform in ['ios', 'gp']:
            platform_name = PLATFORM_NAMES[platform]
            lines.append(f"**{platform_name} — 当前 Top 5**")
            for chart_type in ['free', 'paid', 'grossing']:
                key = f"{platform}_{chart_type}"
                data = analysis['charts'].get(key, {})
                changes = data.get('changes', {})
                # For first crawl, all are "new entries"
                all_apps = changes.get('new_entries', [])[:5]
                if all_apps:
                    emoji = CHART_EMOJI[chart_type]
                    chart_name = CHART_NAMES[chart_type]
                    lines.append(f"  {emoji} {chart_name}:")
                    for app in all_apps:
                        lines.append(f"    {app['rank']}. {app['app_name']} — {app.get('category', '?')}")
            lines.append("")

    report = "\n".join(lines)

    # Discord message limit is 2000 chars
    if len(report) > 1900:
        report = report[:1900] + "\n\n... (报告被截断，完整报告请查看日志)"

    return report


def generate_summary_line(crawl_time=None):
    """Generate a one-line summary for heartbeat checks"""
    analysis = generate_full_analysis(crawl_time)
    if not analysis:
        return "📊 游戏榜单：暂无数据"

    total_surges = 0
    total_new = 0
    for key, data in analysis['charts'].items():
        changes = data.get('changes', {})
        total_surges += len(changes.get('surges', []))
        total_new += len(changes.get('new_entries', []))

    return f"📊 游戏榜单：{total_surges}款飙升，{total_new}款新上榜"


if __name__ == "__main__":
    print(generate_report())
