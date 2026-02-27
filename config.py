"""Game Tracker Configuration"""

import os

# === 数据库 ===
DB_PATH = os.path.join(os.path.dirname(__file__), "rankings.db")

# === 抓取配置 ===
COUNTRY = "us"  # 美国区
TOP_N = 100     # Top 100

# === 榜单类型 ===
# Google Play collections
GP_COLLECTIONS = {
    "free": "TOP_FREE",
    "paid": "TOP_PAID",
    "grossing": "TOP_GROSSING",
}

# iOS App Store 榜单 URL (RSS JSON)
IOS_FEEDS = {
    "free": f"https://rss.applemarketingtools.com/api/v2/{COUNTRY}/apps/top-free/{TOP_N}/apps.json",
    "paid": f"https://rss.applemarketingtools.com/api/v2/{COUNTRY}/apps/top-paid/{TOP_N}/apps.json",
    # 畅销榜没有官方 RSS，用 scraper 补充
}

# === 分析阈值 ===
RANK_SURGE_THRESHOLD = 15      # 排名上升 ≥15 视为飙升
NEW_ENTRY_DAYS = 30            # 上线 ≤30 天视为新游戏
CONSECUTIVE_RISE_DAYS = 3      # 连续上升天数
CATEGORY_TREND_WINDOW = 7      # 品类趋势分析窗口（天）

# === 报告 ===
REPORT_MAX_ITEMS = 10          # 每个板块最多展示条目数
