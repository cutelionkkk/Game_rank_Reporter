"""
Multi-channel notification system.
Supports: Discord, Telegram, Slack, 飞书 (Feishu/Lark), 钉钉 (DingTalk), 企业微信 (WeCom)
"""

import hashlib
import hmac
import json
import time
import base64
import urllib.parse
import traceback
from datetime import datetime

import requests

from config import load_settings, CHANNEL_TEMPLATES


# ============================================================
# Message formatting per channel
# ============================================================

def _markdown_to_plain(text):
    """Strip markdown bold/italic for plain text channels"""
    return text.replace('**', '').replace('*', '').replace('`', '')


def _split_messages(text, max_len=2000):
    """Split long text into chunks at line boundaries"""
    if len(text) <= max_len:
        return [text]

    chunks = []
    current = ""
    for line in text.split('\n'):
        if len(current) + len(line) + 1 > max_len:
            if current:
                chunks.append(current)
            current = line
        else:
            current = current + '\n' + line if current else line
    if current:
        chunks.append(current)
    return chunks


# ============================================================
# Channel Senders
# ============================================================

def send_discord(report, config):
    """Send via Discord Webhook"""
    webhook_url = config.get('webhook_url', '')
    if not webhook_url:
        return False, "Discord webhook_url not configured"

    chunks = _split_messages(report, 2000)
    for chunk in chunks:
        payload = {"content": chunk}

        mention = config.get('mention_role', '')
        if mention and chunk == chunks[0]:
            payload["content"] = f"<@&{mention}>\n{chunk}"

        resp = requests.post(webhook_url, json=payload, timeout=15)
        if resp.status_code not in (200, 204):
            return False, f"Discord API error: {resp.status_code} {resp.text[:200]}"
        time.sleep(0.5)  # rate limit

    return True, f"Sent {len(chunks)} message(s)"


def send_telegram(report, config):
    """Send via Telegram Bot API"""
    bot_token = config.get('bot_token', '')
    chat_id = config.get('chat_id', '')
    if not bot_token or not chat_id:
        return False, "Telegram bot_token or chat_id not configured"

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    # Telegram supports MarkdownV2, but it's finicky
    # Use HTML mode which is more forgiving
    html_report = report.replace('**', '<b>').replace('</b><b>', '')
    # Fix: proper bold tags
    import re
    html_report = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', report)

    chunks = _split_messages(html_report, 4096)
    for chunk in chunks:
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code != 200:
            return False, f"Telegram API error: {resp.status_code} {resp.text[:200]}"
        time.sleep(0.3)

    return True, f"Sent {len(chunks)} message(s)"


def send_slack(report, config):
    """Send via Slack Incoming Webhook"""
    webhook_url = config.get('webhook_url', '')
    if not webhook_url:
        return False, "Slack webhook_url not configured"

    # Slack uses mrkdwn format (similar to markdown)
    # Convert ** bold to * bold
    slack_text = report.replace('**', '*')

    chunks = _split_messages(slack_text, 3000)
    for chunk in chunks:
        payload = {"text": chunk}
        channel = config.get('channel', '')
        if channel:
            payload["channel"] = channel

        resp = requests.post(webhook_url, json=payload, timeout=15)
        if resp.status_code != 200:
            return False, f"Slack error: {resp.status_code} {resp.text[:200]}"
        time.sleep(0.3)

    return True, f"Sent {len(chunks)} message(s)"


def send_feishu(report, config):
    """Send via 飞书 (Feishu/Lark) Custom Bot Webhook"""
    webhook_url = config.get('webhook_url', '')
    if not webhook_url:
        return False, "Feishu webhook_url not configured"

    # Build request with optional signing
    secret = config.get('secret', '')
    headers = {"Content-Type": "application/json; charset=utf-8"}

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "📊 游戏榜单分析报告"
                },
                "template": "blue",
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": report[:30000],  # Feishu card limit
                }
            ],
        },
    }

    if secret:
        timestamp = str(int(time.time()))
        string_to_sign = f"{timestamp}\n{secret}"
        hmac_code = hmac.new(string_to_sign.encode('utf-8'),
                             digestmod=hashlib.sha256).digest()
        sign = base64.b64encode(hmac_code).decode('utf-8')
        payload["timestamp"] = timestamp
        payload["sign"] = sign

    resp = requests.post(webhook_url, json=payload, headers=headers, timeout=15)
    result = resp.json() if resp.headers.get('content-type', '').startswith('application/json') else {}

    if result.get('code', -1) == 0 or resp.status_code == 200:
        return True, "Sent"
    return False, f"Feishu error: {resp.status_code} {resp.text[:200]}"


def send_dingtalk(report, config):
    """Send via 钉钉 (DingTalk) Custom Bot Webhook"""
    webhook_url = config.get('webhook_url', '')
    if not webhook_url:
        return False, "DingTalk webhook_url not configured"

    # Optional signing
    secret = config.get('secret', '')
    if secret:
        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{secret}"
        hmac_code = hmac.new(secret.encode('utf-8'),
                             string_to_sign.encode('utf-8'),
                             digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        webhook_url = f"{webhook_url}&timestamp={timestamp}&sign={sign}"

    # DingTalk markdown message
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": "📊 游戏榜单分析报告",
            "text": report[:20000],  # DingTalk limit
        },
    }

    resp = requests.post(webhook_url, json=payload, timeout=15)
    result = resp.json() if resp.headers.get('content-type', '').startswith('application/json') else {}

    if result.get('errcode', -1) == 0:
        return True, "Sent"
    return False, f"DingTalk error: {result.get('errmsg', resp.text[:200])}"


def send_wechat(report, config):
    """Send via 企业微信 (WeCom) Group Bot Webhook"""
    webhook_url = config.get('webhook_url', '')
    if not webhook_url:
        return False, "WeCom webhook_url not configured"

    # WeCom markdown has a 4096 char limit
    chunks = _split_messages(report, 4000)
    for chunk in chunks:
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": chunk,
            },
        }

        resp = requests.post(webhook_url, json=payload, timeout=15)
        result = resp.json() if resp.headers.get('content-type', '').startswith('application/json') else {}

        if result.get('errcode', -1) != 0:
            return False, f"WeCom error: {result.get('errmsg', resp.text[:200])}"
        time.sleep(0.3)

    return True, f"Sent {len(chunks)} message(s)"


# ============================================================
# Dispatcher
# ============================================================

SENDERS = {
    "discord": send_discord,
    "telegram": send_telegram,
    "slack": send_slack,
    "feishu": send_feishu,
    "dingtalk": send_dingtalk,
    "wechat": send_wechat,
}

CHANNEL_NAMES = {
    "discord": "Discord",
    "telegram": "Telegram",
    "slack": "Slack",
    "feishu": "飞书 (Feishu)",
    "dingtalk": "钉钉 (DingTalk)",
    "wechat": "企业微信 (WeCom)",
}


def send_report(report, channels=None):
    """Send report (single string) to all configured channels"""
    settings = load_settings()
    active_channels = channels or settings.get('notify_channels', [])
    channel_config = settings.get('channel_config', {})

    if not active_channels:
        print("  ℹ️ No notification channels configured")
        return {}

    results = {}
    for ch in active_channels:
        sender = SENDERS.get(ch)
        if not sender:
            results[ch] = (False, f"Unknown channel: {ch}")
            continue

        conf = channel_config.get(ch, {})
        ch_name = CHANNEL_NAMES.get(ch, ch)

        try:
            ok, msg = sender(report, conf)
            results[ch] = (ok, msg)
            status = "✅" if ok else "❌"
            print(f"  {status} {ch_name}: {msg}")
        except Exception as e:
            results[ch] = (False, str(e))
            print(f"  ❌ {ch_name}: {e}")
            traceback.print_exc()

    return results


def send_report_parts(parts: list, channels=None):
    """Send each chart as a separate message to all configured channels"""
    settings = load_settings()
    active_channels = channels or settings.get('notify_channels', [])
    channel_config = settings.get('channel_config', {})

    if not active_channels:
        print("  ℹ️ No notification channels configured")
        return {}

    results = {}
    for ch in active_channels:
        sender = SENDERS.get(ch)
        if not sender:
            results[ch] = (False, f"Unknown channel: {ch}")
            continue

        conf = channel_config.get(ch, {})
        ch_name = CHANNEL_NAMES.get(ch, ch)
        sent = 0
        last_err = None

        try:
            for part in parts:
                ok, msg = sender(part, conf)
                if ok:
                    sent += 1
                else:
                    last_err = msg
                time.sleep(1.2)  # avoid Telegram rate limits (30 msg/sec global, 1/sec per chat)

            if last_err:
                results[ch] = (False, f"Sent {sent}/{len(parts)}, last error: {last_err}")
                print(f"  ⚠️ {ch_name}: Sent {sent}/{len(parts)} messages")
            else:
                results[ch] = (True, f"Sent {sent} message(s)")
                print(f"  ✅ {ch_name}: Sent {sent} message(s)")
        except Exception as e:
            results[ch] = (False, str(e))
            print(f"  ❌ {ch_name}: {e}")
            traceback.print_exc()

    return results


def test_channel(channel_name):
    """Send a test message to a specific channel"""
    test_msg = (
        "📊 **Game Rank Reporter — 测试消息**\n\n"
        "✅ 通知渠道配置成功！\n"
        f"📡 渠道: {CHANNEL_NAMES.get(channel_name, channel_name)}\n"
        f"🕐 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        "后续报告将通过此渠道发送。"
    )

    settings = load_settings()
    conf = settings.get('channel_config', {}).get(channel_name, {})
    sender = SENDERS.get(channel_name)

    if not sender:
        return False, f"Unknown channel: {channel_name}"

    return sender(test_msg, conf)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        ch = sys.argv[2] if len(sys.argv) > 2 else None
        if ch:
            ok, msg = test_channel(ch)
            print(f"{'✅' if ok else '❌'} {msg}")
        else:
            print("Usage: python notify.py test <channel>")
            print(f"Channels: {', '.join(SENDERS.keys())}")
    else:
        # Send latest report to all channels
        from report import generate_report
        report = generate_report()
        send_report(report)
