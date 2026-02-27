"""Game Tracker Configuration"""

import os
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# === 数据库 ===
DB_PATH = os.path.join(SCRIPT_DIR, "rankings.db")

# === 用户配置文件 ===
CONFIG_FILE = os.path.join(SCRIPT_DIR, "settings.json")

# === 默认配置 ===
DEFAULTS = {
    # 抓取
    "country": "us",
    "top_n": 100,
    "charts": ["free", "paid", "grossing"],
    "platforms": ["ios", "gp"],

    # 分析阈值
    "rank_surge_threshold": 15,
    "new_entry_days": 30,
    "consecutive_rise_days": 3,
    "category_trend_window": 7,

    # 报告
    "report_max_items": 10,
    "report_language": "zh",  # zh | en

    # 通知渠道 (可多选)
    "notify_channels": [],
    # 每个渠道的配置
    "channel_config": {},
}

# === 渠道配置模板 ===
CHANNEL_TEMPLATES = {
    "discord": {
        "webhook_url": "",       # Discord Webhook URL
        "mention_role": "",      # 可选: @role ID
    },
    "telegram": {
        "bot_token": "",         # Telegram Bot Token
        "chat_id": "",           # Chat / Group / Channel ID
    },
    "slack": {
        "webhook_url": "",       # Slack Incoming Webhook URL
        "channel": "",           # 可选: #channel-name
    },
    "feishu": {
        "webhook_url": "",       # 飞书自定义机器人 Webhook URL
        "secret": "",            # 可选: 签名密钥
    },
    "dingtalk": {
        "webhook_url": "",       # 钉钉自定义机器人 Webhook URL
        "secret": "",            # 可选: 加签密钥
    },
    "wechat": {
        "webhook_url": "",       # 企业微信群机器人 Webhook URL
    },
}


def load_settings():
    """Load user settings, merge with defaults"""
    settings = DEFAULTS.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                user = json.load(f)
            settings.update(user)
        except Exception as e:
            print(f"⚠️ Failed to load {CONFIG_FILE}: {e}")
    return settings


def save_settings(settings):
    """Save settings to file"""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)


def get_setting(key, default=None):
    """Get a single setting value"""
    s = load_settings()
    return s.get(key, default)


# === 兼容旧代码的全局变量 ===
_settings = load_settings()
COUNTRY = _settings["country"]
TOP_N = _settings["top_n"]
RANK_SURGE_THRESHOLD = _settings["rank_surge_threshold"]
NEW_ENTRY_DAYS = _settings["new_entry_days"]
CONSECUTIVE_RISE_DAYS = _settings["consecutive_rise_days"]
CATEGORY_TREND_WINDOW = _settings["category_trend_window"]
REPORT_MAX_ITEMS = _settings["report_max_items"]

# Legacy
GP_COLLECTIONS = {
    "free": "TOP_FREE",
    "paid": "TOP_PAID",
    "grossing": "TOP_GROSSING",
}

IOS_FEEDS = {
    "free": f"https://rss.applemarketingtools.com/api/v2/{COUNTRY}/apps/top-free/{TOP_N}/apps.json",
    "paid": f"https://rss.applemarketingtools.com/api/v2/{COUNTRY}/apps/top-paid/{TOP_N}/apps.json",
}
