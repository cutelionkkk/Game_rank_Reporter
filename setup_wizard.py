#!/usr/bin/env python3
"""
Interactive setup wizard for Game Rank Reporter.
Configure notification channels via command line.

Usage:
  python setup_wizard.py              # Full interactive setup
  python setup_wizard.py add discord  # Add a specific channel
  python setup_wizard.py remove slack # Remove a channel
  python setup_wizard.py test feishu  # Test a channel
  python setup_wizard.py status       # Show current config
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    load_settings, save_settings, CONFIG_FILE,
    CHANNEL_TEMPLATES, DEFAULTS,
)
from notify import test_channel, CHANNEL_NAMES, SENDERS


def print_banner():
    print()
    print("🎮 Game Rank Reporter — Setup Wizard")
    print("=" * 45)


def show_status():
    """Show current configuration"""
    settings = load_settings()
    channels = settings.get('notify_channels', [])
    channel_config = settings.get('channel_config', {})

    print(f"\n📋 当前配置:")
    print(f"  🌍 地区: {settings.get('country', 'us').upper()}")
    print(f"  📊 Top N: {settings.get('top_n', 100)}")
    print(f"  📈 榜单: {', '.join(settings.get('charts', ['free', 'paid', 'grossing']))}")
    print(f"  📱 平台: {', '.join(settings.get('platforms', ['ios', 'gp']))}")
    print()

    if channels:
        print(f"  📡 通知渠道 ({len(channels)}个):")
        for ch in channels:
            name = CHANNEL_NAMES.get(ch, ch)
            conf = channel_config.get(ch, {})
            # Check if configured
            has_config = any(v for v in conf.values() if v)
            status = "✅ 已配置" if has_config else "⚠️ 未配置"
            print(f"    - {name}: {status}")
    else:
        print("  📡 通知渠道: 无 (报告仅保存到本地文件)")

    print(f"\n  📁 配置文件: {CONFIG_FILE}")
    print()


def add_channel(channel_name=None):
    """Add and configure a notification channel"""
    settings = load_settings()
    channels = settings.get('notify_channels', [])
    channel_config = settings.get('channel_config', {})

    if not channel_name:
        print("\n📡 可用渠道:")
        available = []
        for i, (key, name) in enumerate(CHANNEL_NAMES.items(), 1):
            in_use = "✅" if key in channels else "  "
            print(f"  {in_use} {i}. {name} ({key})")
            available.append(key)

        choice = input("\n选择渠道编号或名称: ").strip()

        # Accept number or name
        if choice.isdigit() and 1 <= int(choice) <= len(available):
            channel_name = available[int(choice) - 1]
        elif choice in SENDERS:
            channel_name = choice
        else:
            print(f"❌ 无效选择: {choice}")
            return

    if channel_name not in SENDERS:
        print(f"❌ 未知渠道: {channel_name}")
        print(f"   可用: {', '.join(SENDERS.keys())}")
        return

    name = CHANNEL_NAMES.get(channel_name, channel_name)
    template = CHANNEL_TEMPLATES.get(channel_name, {})

    print(f"\n⚙️ 配置 {name}")
    print("-" * 30)

    # Get existing config or template
    existing = channel_config.get(channel_name, {})
    new_config = {}

    for key, default_val in template.items():
        current = existing.get(key, default_val)
        hint = f" (当前: {current[:30]}...)" if current else ""
        label = _friendly_label(channel_name, key)

        val = input(f"  {label}{hint}: ").strip()
        new_config[key] = val if val else current

    # Save
    channel_config[channel_name] = new_config
    if channel_name not in channels:
        channels.append(channel_name)

    settings['notify_channels'] = channels
    settings['channel_config'] = channel_config
    save_settings(settings)

    print(f"\n✅ {name} 已配置")

    # Offer to test
    do_test = input("  发送测试消息? (y/n): ").strip().lower()
    if do_test == 'y':
        print(f"  发送中...")
        ok, msg = test_channel(channel_name)
        print(f"  {'✅' if ok else '❌'} {msg}")


def remove_channel(channel_name=None):
    """Remove a notification channel"""
    settings = load_settings()
    channels = settings.get('notify_channels', [])

    if not channel_name:
        if not channels:
            print("  ℹ️ 没有已配置的渠道")
            return
        print("\n当前渠道:")
        for i, ch in enumerate(channels, 1):
            print(f"  {i}. {CHANNEL_NAMES.get(ch, ch)}")
        choice = input("选择要移除的编号: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(channels):
            channel_name = channels[int(choice) - 1]
        else:
            print("❌ 无效选择")
            return

    if channel_name in channels:
        channels.remove(channel_name)
        settings['notify_channels'] = channels
        # Keep config in case they re-add
        save_settings(settings)
        print(f"✅ {CHANNEL_NAMES.get(channel_name, channel_name)} 已移除")
    else:
        print(f"ℹ️ {channel_name} 不在已配置渠道中")


def run_test(channel_name=None):
    """Test a channel"""
    settings = load_settings()
    channels = settings.get('notify_channels', [])

    if not channel_name:
        if not channels:
            print("  ℹ️ 没有已配置的渠道")
            return
        for i, ch in enumerate(channels, 1):
            print(f"  {i}. {CHANNEL_NAMES.get(ch, ch)}")
        choice = input("选择要测试的编号: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(channels):
            channel_name = channels[int(choice) - 1]

    if channel_name:
        print(f"  发送测试消息到 {CHANNEL_NAMES.get(channel_name, channel_name)}...")
        ok, msg = test_channel(channel_name)
        print(f"  {'✅' if ok else '❌'} {msg}")


def _friendly_label(channel, key):
    """Human-friendly labels for config keys"""
    labels = {
        ('discord', 'webhook_url'): 'Webhook URL',
        ('discord', 'mention_role'): 'Role ID to mention (可选)',
        ('telegram', 'bot_token'): 'Bot Token (@BotFather)',
        ('telegram', 'chat_id'): 'Chat/Group/Channel ID',
        ('slack', 'webhook_url'): 'Incoming Webhook URL',
        ('slack', 'channel'): 'Channel (可选, 如 #game-alerts)',
        ('feishu', 'webhook_url'): '自定义机器人 Webhook URL',
        ('feishu', 'secret'): '签名密钥 (可选)',
        ('dingtalk', 'webhook_url'): '自定义机器人 Webhook URL',
        ('dingtalk', 'secret'): '加签密钥 (可选)',
        ('wechat', 'webhook_url'): '群机器人 Webhook URL',
    }
    return labels.get((channel, key), key)


def interactive_setup():
    """Full interactive setup"""
    print_banner()
    show_status()

    while True:
        print("\n操作:")
        print("  1. 添加通知渠道")
        print("  2. 移除通知渠道")
        print("  3. 测试通知渠道")
        print("  4. 查看当前配置")
        print("  5. 退出")

        choice = input("\n选择 (1-5): ").strip()

        if choice == '1':
            add_channel()
        elif choice == '2':
            remove_channel()
        elif choice == '3':
            run_test()
        elif choice == '4':
            show_status()
        elif choice == '5':
            print("\n👋 配置已保存")
            break
        else:
            print("❌ 无效选择")


def main():
    if len(sys.argv) < 2:
        interactive_setup()
        return

    cmd = sys.argv[1]
    arg = sys.argv[2] if len(sys.argv) > 2 else None

    if cmd == 'add':
        add_channel(arg)
    elif cmd == 'remove':
        remove_channel(arg)
    elif cmd == 'test':
        run_test(arg)
    elif cmd == 'status':
        show_status()
    elif cmd == 'help':
        print(__doc__)
    else:
        print(f"❌ Unknown command: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
