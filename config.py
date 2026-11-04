"""Game Tracker Configuration"""

import os
import json
import copy
import re
import tempfile

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
    "comparison_hours": 24,  # 0 compares with the previous successful snapshot
    "ranking_enabled": True,
    "company_enabled": True,
    "companies": [],
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
    "feishu_bot": {
        "app_id": "",             # 推荐通过 FEISHU_APP_ID 环境变量设置
        "app_secret": "",         # 推荐通过 FEISHU_APP_SECRET 环境变量设置
        # 接收人通过 FEISHU_RECIPIENTS 环境变量设置，避免进入网页配置。
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
    settings = copy.deepcopy(DEFAULTS)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                user = json.load(f)
            settings.update(user)
        except (OSError, ValueError) as e:
            raise ValueError(f"无法读取配置，请检查 settings.json：{e}") from e
    return settings


def save_settings(settings):
    """Save settings to file"""
    fd, path = tempfile.mkstemp(prefix='.settings-', suffix='.tmp',
                                dir=os.path.dirname(CONFIG_FILE))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
            f.write('\n')
        os.replace(path, CONFIG_FILE)
    finally:
        if os.path.exists(path):
            os.unlink(path)


def get_setting(key, default=None):
    """Get a single setting value"""
    s = load_settings()
    return s.get(key, default)


MONITOR_KEYS = ('ranking_enabled', 'company_enabled', 'top_n',
                'rank_surge_threshold', 'comparison_hours', 'new_entry_days',
                'report_max_items', 'chart_list', 'companies')


def country_code(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z]{2}', value):
        raise ValueError('国家/地区请填写两位代码，例如 us、jp、cn')
    return value.lower()


def chart_scopes(settings=None, enabled_only=True):
    """Normalize old configuration, respecting an explicitly empty selection."""
    s = settings if settings is not None else load_settings()
    if enabled_only and not s.get('ranking_enabled', True):
        return []
    charts = s.get('chart_list')
    if charts is None:
        charts = [dict(platform=p, chart_type=c, genre='all')
                  for p in s['platforms'] for c in s['charts']]
    return [dict(c, country=c.get('country', s.get('country', 'us')).lower(),
                 genre=c.get('genre', 'all'), enabled=c.get('enabled', True))
            for c in charts if not enabled_only or c.get('enabled', True)]


def monitor_settings(settings=None):
    """Public settings only: notification secrets never enter the browser."""
    s = settings if settings is not None else load_settings()
    result = {k: copy.deepcopy(s.get(k, DEFAULTS.get(k))) for k in MONITOR_KEYS}
    result['chart_list'] = chart_scopes(s, enabled_only=False)
    return result


def validate_monitor_settings(payload):
    from genres import GENRES, CHART_TYPES, PLATFORMS
    if not isinstance(payload, dict) or set(payload) != set(MONITOR_KEYS):
        raise ValueError('监测配置字段不完整或包含不支持的字段')
    s = copy.deepcopy(payload)
    for key in ('ranking_enabled', 'company_enabled'):
        if type(s[key]) is not bool:
            raise ValueError(f'{key} 必须是开关')
    for key, low, high in [('top_n', 10, 200), ('rank_surge_threshold', 1, 199),
                           ('new_entry_days', 1, 365), ('report_max_items', 1, 30)]:
        if type(s[key]) is not int or not low <= s[key] <= high:
            raise ValueError(f'{key} 必须在 {low}–{high} 之间')
    if type(s['comparison_hours']) is not int or s['comparison_hours'] not in (0, 24, 72, 168):
        raise ValueError('对比窗口请选择上次、24 小时、72 小时或 7 天')
    if not isinstance(s['chart_list'], list) or len(s['chart_list']) > 100:
        raise ValueError('最多保存 100 个榜单版块')
    scopes = set()
    for c in s['chart_list']:
        if not isinstance(c, dict):
            raise ValueError('榜单格式无效')
        p, chart, genre = c.get('platform'), c.get('chart_type'), c.get('genre')
        if p not in PLATFORMS or chart not in CHART_TYPES or genre not in GENRES:
            raise ValueError('商店、榜单类型或游戏品类无效')
        field = 'ios_genre_id' if p == 'ios' else 'gp_category'
        if not GENRES[genre].get(field):
            raise ValueError(f'{p} 不支持品类 {genre}')
        c['country'] = country_code(c.get('country'))
        if type(c.get('enabled')) is not bool:
            raise ValueError('版块启用状态无效')
        key = (p, c['country'], chart, genre)
        if key in scopes:
            raise ValueError('请移除重复的榜单版块')
        scopes.add(key)
    if not isinstance(s['companies'], list) or len(s['companies']) > 50:
        raise ValueError('最多关注 50 个开发者账号')
    ids, accounts = set(), set()
    for company in s['companies']:
        if not isinstance(company, dict):
            raise ValueError('公司配置无效')
        for key in ('id', 'name', 'developer_id'):
            value = company.get(key)
            if not isinstance(value, str) or not value.strip() or len(value) > 200:
                raise ValueError('请填写公司名称和有效的开发者 ID')
            company[key] = value.strip()
        if company['id'] in ids:
            raise ValueError('公司配置 ID 重复')
        ids.add(company['id'])
        p = company.get('platform')
        if p not in PLATFORMS or type(company.get('enabled')) is not bool:
            raise ValueError('公司商店或启用状态无效')
        if p == 'ios' and not company['developer_id'].isdigit():
            raise ValueError('App Store 开发者 ID 必须为数字，请从搜索结果或开发者页面获取')
        if any(ord(c) < 32 for c in company['developer_id']):
            raise ValueError('开发者 ID 包含无效字符')
        key = (p, company['developer_id'])
        if key in accounts:
            raise ValueError('同一开发者账号请合并为一项，勾选多个国家即可')
        accounts.add(key)
        countries = company.get('countries')
        if not isinstance(countries, list) or not 1 <= len(countries) <= 10:
            raise ValueError('每个开发者请选择 1–10 个国家/地区')
        company['countries'] = list(dict.fromkeys(country_code(c) for c in countries))
    return s


def save_monitor_settings(payload):
    validated = validate_monitor_settings(payload)
    settings = load_settings()
    settings.update(validated)
    save_settings(settings)
    return monitor_settings(settings)


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
