"""Manual review of actual ranking history and watched publishers' recent releases."""
import json
from collections import defaultdict
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from analyzer import analyze_chart_changes, generate_full_analysis
from config import load_settings
from database import get_rankings_at, parse_time, query
from publishers import release_age_days
from report import PLATFORM_NAMES
from product_links import product_link


def text(value, limit=120):
    return escape(str(value or '')[:limit])


def release_day(value):
    try:
        return parse_time(value).date().isoformat()
    except (ValueError, TypeError):
        for fmt in ('%b %d, %Y', '%B %d, %Y'):
            try:
                return datetime.strptime(value, fmt).date().isoformat()
            except (ValueError, TypeError):
                pass
    return '日期未知'


def review_analysis(crawl_time, settings=None):
    settings = settings or load_settings()
    analysis = generate_full_analysis(crawl_time, settings)
    for chart in analysis['charts'].values():
        chart['short_history'] = False
        if chart['status'] != 'ok' or chart['previous_time']:
            continue
        scope = chart['scope']
        # Pick the oldest available observation within the requested window;
        # never select a baseline because it produces a larger movement.
        rows = query('''SELECT crawl_time FROM rankings WHERE platform=? AND country=? AND chart_type=?
            AND julianday(crawl_time)<julianday(?) AND julianday(crawl_time)>=julianday(?)-?
            ORDER BY julianday(crawl_time) LIMIT 1''',
            (scope['platform'],scope['country'],chart['db_chart_type'],crawl_time,crawl_time,
             (settings['comparison_hours'] or 24)/24))
        if not rows:
            continue
        previous = rows[0]['crawl_time']
        chart.update(previous_time=previous,short_history=True,
                     elapsed_hours=(parse_time(crawl_time)-parse_time(previous)).total_seconds()/3600,
                     changes=analyze_chart_changes(scope['platform'],chart['db_chart_type'],crawl_time,
                                                   previous,scope['country'],settings))
    return analysis


def company_blocks(analysis, settings):
    groups = defaultdict(list)
    for data in analysis['companies']:
        c = data['company']
        groups[c.get('group') or c['name']].append(data)
    if not groups:
        return []
    blocks = [f"<b>🏢 关注公司 · 近 {settings['new_entry_days']} 天商店首发</b>\n含已在目录中的产品，不等同于今天新发布。"]
    for group, members in groups.items():
        recent, discovered = {}, {}
        incomplete = 0
        for data in members:
            c = data['company']
            snaps = data['snapshots']
            incomplete += int(len(snaps)<len(c['countries']) or any(s['status']!='ok' for s in snaps))
            rows = query('''SELECT country,data_json FROM publisher_apps
                WHERE platform=? AND developer_id=? AND last_seen=?''',
                (c['platform'],c['developer_id'],analysis['crawl_time']))
            for row in rows:
                if row['country'] not in c['countries']:
                    continue
                app = json.loads(row['data_json'])
                age = release_age_days(app.get('release_date'),analysis['crawl_time'])
                if app.get('is_game') and age is not None and 0<=age<=settings['new_entry_days']:
                    key = (c['platform'],app['app_id'])
                    item = recent.setdefault(key,dict(app=app,platform=c['platform'],age=age,countries=set()))
                    item['countries'].add(row['country'].upper())
            for event in data['events']:
                if event['kind'] == 'newly_discovered':
                    discovered[(c['platform'],event['app_id'])] = event
        lines = ['<b>'+text(group)+'</b>']
        ordered = sorted(recent.values(),key=lambda a:(a['age'],a['app']['app_name']))
        for item in ordered[:settings['report_max_items']]:
            app = item['app']
            country = sorted(item['countries'])[0].lower()
            lines.append(f"• <b>{product_link(app, item['platform'], country)}</b>\n  {PLATFORM_NAMES[item['platform']]} · {','.join(sorted(item['countries']))} · {release_day(app['release_date'])}")
        if len(ordered)>settings['report_max_items']:
            lines.append(f"另有 {len(ordered)-settings['report_max_items']} 个商店条目。")
        if not ordered:
            lines.append('可用目录中未查到可确认的近期首发游戏。')
        for (platform,app_id),e in list(discovered.items())[:3]:
            lines.append('首次发现（未确认为近期首发）：'+product_link(e, platform, e['country']))
        if incomplete:
            lines.append(f'{incomplete} 个账号目录暂不完整，继续复查。')
        blocks.append('\n'.join(lines))
    return blocks


def generate_trial_review(crawl_time):
    settings = load_settings()
    analysis = review_analysis(crawl_time, settings)
    parts = ['<b>试推补充 · 美国免费榜与竞品动态</b>\nApp Store + Google Play · 全部游戏 · 采集 Top 100']
    parts.append(f"<b>📈 榜单爬升</b>\n上涨提醒阈值：{settings['rank_surge_threshold']} 名；以下按实际历史间隔比较。")
    for chart in analysis['charts'].values():
        scope = chart['scope']
        lines = ['<b>'+PLATFORM_NAMES[scope['platform']]+' · 美国免费榜</b>']
        if chart['status']!='ok':
            lines.append('本轮未取得榜单：'+text(chart.get('message')))
        elif not chart['previous_time']:
            lines.append('暂无可比历史；以下仅为当前排名快照（前 10 名）。')
            lines.extend(f"#{a['rank']}  {product_link(a, scope['platform'], scope['country'])}" for a in chart['current'][:10])
        else:
            start = parse_time(chart['previous_time']).astimezone(ZoneInfo('Asia/Shanghai'))
            end = parse_time(crawl_time).astimezone(ZoneInfo('Asia/Shanghai'))
            minutes = round((end-start).total_seconds()/60)
            lines.append(f'{start:%m-%d %H:%M} → {end:%m-%d %H:%M}（北京时间，间隔 {minutes} 分钟）')
            if chart['short_history']:
                lines.append('不足设定窗口，属于短时变化。')
            changes = chart['changes']
            movers = changes['top_movers_up']
            if not changes['surges']:
                lines.append(f"暂无达到 ↑{settings['rank_surge_threshold']} 的项目。")
            for app in movers[:settings['report_max_items']]:
                lines.append(f"• <b>{product_link(app, scope['platform'], scope['country'])}</b>\n  #{app['prev_rank']} → #{app['rank']}（↑{app['rank_change']}）")
            if not movers:
                lines.append('这段时间未检测到排名上涨。')
            old = get_rankings_at(chart['previous_time'],scope['platform'],chart['db_chart_type'],scope['country'])
            depth = min(max(a['rank'] for a in old),max(a['rank'] for a in chart['current']))
            if changes['new_entries']:
                lines.append(f'新进可比 Top {depth}：'+ '、'.join(f"{product_link(a, scope['platform'], scope['country'],60)} #{a['rank']}" for a in changes['new_entries'][:3]))
            if depth<settings['top_n']:
                lines.append(f'旧快照仅 Top {depth}，扩大的采集范围不算新上榜。')
        parts.append('\n'.join(lines))
    parts.extend(company_blocks(analysis,settings))
    return parts
