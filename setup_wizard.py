#!/usr/bin/env python3
"""Interactive setup wizard for Game Rank Reporter"""

import sys
import json
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import load_settings, save_settings, CHANNEL_TEMPLATES
from genres import (
    GENRES, CHART_TYPES, PLATFORMS, PRESETS,
    list_genres, list_presets, format_chart_label, get_genre_display,
)


def _input(prompt, default=None):
    if default:
        val = input(f"{prompt} [{default}]: ").strip()
        return val if val else default
    return input(f"{prompt}: ").strip()


def _yes_no(prompt, default=True):
    d = "Y/n" if default else "y/N"
    val = input(f"{prompt} [{d}]: ").strip().lower()
    if not val:
        return default
    return val in ('y', 'yes')


# ============================================================
# Chart / Genre configuration
# ============================================================

def setup_charts():
    """Interactive chart selection"""
    settings = load_settings()
    
    print("\n" + "=" * 50)
    print("📊 配置追踪榜单")
    print("=" * 50)
    print()
    print("选择方式：")
    print("  1. 使用预设方案（推荐新手）")
    print("  2. 自定义选择榜单")
    print("  3. 查看当前配置")
    print()
    
    choice = _input("请选择", "1")
    
    if choice == "3":
        show_current_charts(settings)
        return
    elif choice == "2":
        chart_list = custom_chart_selection()
    else:
        chart_list = preset_selection()
    
    if chart_list:
        settings['chart_list'] = chart_list
        save_settings(settings)
        print(f"\n✅ 已保存！共 {len(chart_list)} 个榜单：")
        for c in chart_list:
            label = format_chart_label(c['platform'], c['chart_type'], c.get('genre', 'all'))
            print(f"  📋 {label}")


def preset_selection():
    """Let user pick a preset"""
    presets = list_presets()
    
    print("\n📋 预设方案：")
    for i, p in enumerate(presets, 1):
        print(f"  {i}. {p['name']}")
        print(f"     {p['description']} ({p['chart_count']} 个榜单)")
    print()
    
    idx = _input("选择预设", "1")
    try:
        idx = int(idx) - 1
        if 0 <= idx < len(presets):
            preset_id = presets[idx]['id']
            preset = PRESETS[preset_id]
            
            print(f"\n已选: {preset.get('name_zh', preset_id)}")
            print("包含的榜单：")
            for c in preset['charts']:
                label = format_chart_label(c['platform'], c['chart_type'], c.get('genre', 'all'))
                print(f"  📋 {label}")
            
            if _yes_no("\n确认使用这个方案？"):
                return preset['charts']
    except (ValueError, IndexError):
        pass
    
    print("❌ 无效选择")
    return None


def custom_chart_selection():
    """Custom chart selection — step by step"""
    chart_list = []
    
    print("\n🔧 自定义榜单选择")
    print("─" * 40)
    
    # Step 1: platforms
    print("\n📱 选择平台（多选用逗号分隔）：")
    print("  1. iOS App Store")
    print("  2. Google Play")
    print("  3. 两个都要")
    p_choice = _input("选择", "3")
    
    platforms = []
    if p_choice == "1":
        platforms = ["ios"]
    elif p_choice == "2":
        platforms = ["gp"]
    else:
        platforms = ["ios", "gp"]
    
    # Step 2: chart types
    print("\n📊 选择榜单类型（多选用逗号分隔）：")
    print("  1. 免费榜")
    print("  2. 付费榜")
    print("  3. 畅销榜")
    print("  4. 全部")
    c_choice = _input("选择", "4")
    
    if c_choice == "1":
        chart_types = ["free"]
    elif c_choice == "2":
        chart_types = ["paid"]
    elif c_choice == "3":
        chart_types = ["grossing"]
    else:
        chart_types = ["free", "paid", "grossing"]
    
    # Step 3: genre selection
    print("\n🎮 选择游戏品类：")
    print("  0. 全部游戏（总榜）")
    
    genres_list = list_genres()
    # Show non-"all" genres
    displayable = [g for g in genres_list if g['id'] != 'all']
    for i, g in enumerate(displayable, 1):
        print(f"  {i}. {g['name']} ({g['id']})")
    
    print()
    print("💡 输入编号选择，多选用逗号分隔")
    print("   例: 0,7,10 = 总榜 + 休闲 + 益智")
    print("   直接回车 = 只选总榜")
    
    g_choice = _input("选择品类", "0")
    
    selected_genres = set()
    for part in g_choice.split(','):
        part = part.strip()
        if part == '0':
            selected_genres.add('all')
        else:
            try:
                idx = int(part) - 1
                if 0 <= idx < len(displayable):
                    selected_genres.add(displayable[idx]['id'])
            except ValueError:
                # Maybe they typed the genre name
                if part in GENRES:
                    selected_genres.add(part)
    
    if not selected_genres:
        selected_genres = {'all'}
    
    # Build chart list
    for p in platforms:
        for c in chart_types:
            for g in sorted(selected_genres):
                # Check platform availability
                genre_info = GENRES.get(g, {})
                if p == 'ios' and genre_info.get('ios_genre_id') is None:
                    print(f"  ⚠️ 跳过: {g} 在 iOS 上不可用")
                    continue
                if p == 'gp' and genre_info.get('gp_category') is None:
                    print(f"  ⚠️ 跳过: {g} 在 GP 上不可用")
                    continue
                chart_list.append({
                    "platform": p,
                    "chart_type": c,
                    "genre": g,
                })
    
    if not chart_list:
        print("❌ 没有有效的榜单组合")
        return None
    
    print(f"\n📋 将追踪 {len(chart_list)} 个榜单：")
    for c in chart_list:
        label = format_chart_label(c['platform'], c['chart_type'], c.get('genre', 'all'))
        print(f"  ✅ {label}")
    
    if _yes_no("\n确认？"):
        return chart_list
    return None


def show_current_charts(settings=None):
    """Display current chart configuration"""
    settings = settings or load_settings()
    chart_list = settings.get('chart_list')
    
    if chart_list:
        print(f"\n📋 当前配置: {len(chart_list)} 个榜单")
        for c in chart_list:
            label = format_chart_label(c['platform'], c['chart_type'], c.get('genre', 'all'))
            print(f"  📊 {label}")
    else:
        platforms = settings.get('platforms', ['ios', 'gp'])
        charts = settings.get('charts', ['free', 'paid', 'grossing'])
        total = len(platforms) * len(charts)
        print(f"\n📋 当前配置: 默认模式（{total} 个榜单，全品类）")
        for p in platforms:
            for c in charts:
                label = format_chart_label(p, c, 'all')
                print(f"  📊 {label}")
    print()


# ============================================================
# Channel configuration (existing)
# ============================================================

def add_channel(channel_name=None):
    """Add or update a notification channel"""
    settings = load_settings()
    
    if not channel_name:
        print("\n📡 可用通知渠道：")
        for i, (name, _) in enumerate(CHANNEL_TEMPLATES.items(), 1):
            active = "✅" if name in settings.get('notify_channels', []) else "  "
            print(f"  {active} {i}. {name}")
        idx = _input("\n选择渠道编号")
        try:
            channel_name = list(CHANNEL_TEMPLATES.keys())[int(idx) - 1]
        except (ValueError, IndexError):
            print("❌ 无效选择")
            return
    
    if channel_name not in CHANNEL_TEMPLATES:
        print(f"❌ 未知渠道: {channel_name}")
        return
    
    template = CHANNEL_TEMPLATES[channel_name]
    config = settings.get('channel_config', {}).get(channel_name, {})
    
    print(f"\n🔧 配置 {channel_name}")
    for key, default in template.items():
        current = config.get(key, default)
        hint = f" (当前: {current[:30]}...)" if current else ""
        val = _input(f"  {key}{hint}")
        if val:
            config[key] = val
        elif current:
            config[key] = current
    
    if 'channel_config' not in settings:
        settings['channel_config'] = {}
    settings['channel_config'][channel_name] = config
    
    if channel_name not in settings.get('notify_channels', []):
        settings.setdefault('notify_channels', []).append(channel_name)
    
    save_settings(settings)
    print(f"✅ {channel_name} 已配置")


def test_channel(channel_name):
    """Test a notification channel"""
    from notify import test_channel as _test
    success = _test(channel_name)
    if success:
        print(f"✅ {channel_name} 测试成功")
    else:
        print(f"❌ {channel_name} 测试失败")


def show_status():
    """Show current configuration status"""
    settings = load_settings()
    
    print("\n📊 Game Rank Reporter 配置状态")
    print("=" * 40)
    
    # Charts
    show_current_charts(settings)
    
    # Channels
    channels = settings.get('notify_channels', [])
    print(f"📡 通知渠道: {len(channels)} 个")
    for ch in channels:
        config = settings.get('channel_config', {}).get(ch, {})
        has_url = any(v for v in config.values())
        status = "✅ 已配置" if has_url else "⚠️ 未配置"
        print(f"  {status} {ch}")
    
    if not channels:
        print("  (未配置任何渠道)")
    
    # Settings
    print(f"\n⚙️ 其他设置:")
    print(f"  国家: {settings.get('country', 'us')}")
    print(f"  Top N: {settings.get('top_n', 100)}")
    print(f"  飙升阈值: ≥{settings.get('rank_surge_threshold', 15)} 名")
    print()


# ============================================================
# Main
# ============================================================

def interactive_setup():
    """Full interactive setup"""
    print("\n🎮 Game Rank Reporter 配置向导")
    print("=" * 40)
    
    while True:
        print("\n选择操作：")
        print("  1. 配置追踪榜单（品类选择）")
        print("  2. 添加通知渠道")
        print("  3. 测试通知渠道")
        print("  4. 查看当前配置")
        print("  5. 退出")
        
        choice = _input("\n选择", "5")
        
        if choice == "1":
            setup_charts()
        elif choice == "2":
            add_channel()
        elif choice == "3":
            channel = _input("渠道名称 (discord/telegram/slack/feishu/dingtalk/wechat)")
            if channel:
                test_channel(channel)
        elif choice == "4":
            show_status()
        else:
            break
    
    print("\n👋 配置完成！运行 python run.py 开始追踪。")


def main():
    args = sys.argv[1:]
    
    if not args:
        interactive_setup()
        return
    
    cmd = args[0]
    
    if cmd == 'charts':
        setup_charts()
    elif cmd == 'add':
        channel = args[1] if len(args) > 1 else None
        add_channel(channel)
    elif cmd == 'test':
        if len(args) > 1:
            test_channel(args[1])
        else:
            print("Usage: setup_wizard.py test <channel_name>")
    elif cmd == 'status':
        show_status()
    elif cmd == 'presets':
        for p in list_presets():
            print(f"  {p['id']}: {p['name']} ({p['chart_count']} charts)")
    elif cmd == 'genres':
        platform = args[1] if len(args) > 1 else None
        for g in list_genres(platform):
            print(f"  {g['id']:15s} {g['name']}")
    else:
        print(f"Unknown command: {cmd}")
        print("Commands: charts, add, test, status, presets, genres")


if __name__ == "__main__":
    main()
