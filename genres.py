"""
Game genre/subcategory definitions for iOS and Google Play.

Design: unified genre system with per-platform mapping.
Users pick genres by name (e.g. "casual", "puzzle"); the system maps to:
  - iOS: iTunes RSS genre ID (e.g. 7003 for Arcade)
  - GP:  google-play-scraper category constant (e.g. GAME_CASUAL)
"""

# === Unified Genre Registry ===
# key: internal genre id (user-facing in config)
# name_zh / name_en: display names
# ios_genre_id: iTunes RSS genre parameter (None = not available on iOS)
# gp_category: google-play-scraper category string (None = not available on GP)

GENRES = {
    "all": {
        "name_zh": "全部游戏",
        "name_en": "All Games",
        "ios_genre_id": 6014,
        "gp_category": "GAME",
    },
    "action": {
        "name_zh": "动作",
        "name_en": "Action",
        "ios_genre_id": 7001,
        "gp_category": "GAME_ACTION",
    },
    "adventure": {
        "name_zh": "冒险",
        "name_en": "Adventure",
        "ios_genre_id": 7002,
        "gp_category": "GAME_ADVENTURE",
    },
    "arcade": {
        "name_zh": "街机",
        "name_en": "Arcade",
        "ios_genre_id": 7003,
        "gp_category": "GAME_ARCADE",
    },
    "board": {
        "name_zh": "棋盘",
        "name_en": "Board",
        "ios_genre_id": 7004,
        "gp_category": "GAME_BOARD",
    },
    "card": {
        "name_zh": "卡牌",
        "name_en": "Card",
        "ios_genre_id": 7005,
        "gp_category": "GAME_CARD",
    },
    "casino": {
        "name_zh": "博彩",
        "name_en": "Casino",
        "ios_genre_id": 7006,
        "gp_category": "GAME_CASINO",
    },
    "casual": {
        "name_zh": "休闲",
        "name_en": "Casual",
        "ios_genre_id": 7009,
        "gp_category": "GAME_CASUAL",
    },
    "educational": {
        "name_zh": "教育",
        "name_en": "Educational",
        "ios_genre_id": None,  # iOS 没有独立的教育游戏分类
        "gp_category": "GAME_EDUCATIONAL",
    },
    "music": {
        "name_zh": "音乐",
        "name_en": "Music",
        "ios_genre_id": 7011,
        "gp_category": "GAME_MUSIC",
    },
    "puzzle": {
        "name_zh": "益智",
        "name_en": "Puzzle",
        "ios_genre_id": 7012,
        "gp_category": "GAME_PUZZLE",
    },
    "racing": {
        "name_zh": "竞速",
        "name_en": "Racing",
        "ios_genre_id": 7013,
        "gp_category": "GAME_RACING",
    },
    "rpg": {
        "name_zh": "角色扮演",
        "name_en": "Role Playing",
        "ios_genre_id": 7014,
        "gp_category": "GAME_ROLE_PLAYING",
    },
    "simulation": {
        "name_zh": "模拟",
        "name_en": "Simulation",
        "ios_genre_id": 7015,
        "gp_category": "GAME_SIMULATION",
    },
    "sports": {
        "name_zh": "体育",
        "name_en": "Sports",
        "ios_genre_id": 7016,
        "gp_category": "GAME_SPORTS",
    },
    "strategy": {
        "name_zh": "策略",
        "name_en": "Strategy",
        "ios_genre_id": 7017,
        "gp_category": "GAME_STRATEGY",
    },
    "trivia": {
        "name_zh": "问答",
        "name_en": "Trivia",
        "ios_genre_id": 7018,
        "gp_category": "GAME_TRIVIA",
    },
    "word": {
        "name_zh": "文字",
        "name_en": "Word",
        "ios_genre_id": 7019,
        "gp_category": "GAME_WORD",
    },
}

# Chart types
CHART_TYPES = {
    "free":     {"name_zh": "免费榜",  "name_en": "Top Free"},
    "paid":     {"name_zh": "付费榜",  "name_en": "Top Paid"},
    "grossing": {"name_zh": "畅销榜",  "name_en": "Top Grossing"},
}

# Platforms
PLATFORMS = {
    "ios": {"name_zh": "iOS App Store", "name_en": "iOS App Store"},
    "gp":  {"name_zh": "Google Play",   "name_en": "Google Play"},
}


def get_genre(genre_id):
    """Get genre info by ID"""
    return GENRES.get(genre_id)


def get_genre_display(genre_id, lang="zh"):
    """Get display name for a genre"""
    g = GENRES.get(genre_id)
    if not g:
        return genre_id
    return g[f"name_{lang}"] if f"name_{lang}" in g else g["name_en"]


def list_genres(platform=None, lang="zh"):
    """List available genres, optionally filtered by platform"""
    result = []
    for gid, info in GENRES.items():
        if platform == "ios" and info["ios_genre_id"] is None:
            continue
        if platform == "gp" and info["gp_category"] is None:
            continue
        name = info.get(f"name_{lang}", info["name_en"])
        result.append({"id": gid, "name": name, "info": info})
    return result


def format_chart_label(platform, chart_type, genre_id, lang="zh"):
    """Generate a human-readable label like 'iOS 休闲游戏免费榜'"""
    p = PLATFORMS.get(platform, {})
    c = CHART_TYPES.get(chart_type, {})
    g = GENRES.get(genre_id, {})

    pname = p.get(f"name_{lang}", platform)
    cname = c.get(f"name_{lang}", chart_type)
    gname = g.get(f"name_{lang}", genre_id)

    if genre_id == "all":
        return f"{pname} 游戏{cname}"
    return f"{pname} {gname}游戏{cname}"


# === Preset Profiles ===
# 常用配置组合，方便用户快速选择

PRESETS = {
    "basic": {
        "name_zh": "基础版 — 全品类 Top 100",
        "name_en": "Basic — All Games Top 100",
        "description_zh": "追踪 iOS + GP 游戏总榜（免费/付费/畅销），每 12 小时 6 个榜单",
        "charts": [
            {"platform": "ios", "chart_type": "free",     "genre": "all"},
            {"platform": "ios", "chart_type": "paid",     "genre": "all"},
            {"platform": "ios", "chart_type": "grossing", "genre": "all"},
            {"platform": "gp",  "chart_type": "free",     "genre": "all"},
            {"platform": "gp",  "chart_type": "paid",     "genre": "all"},
            {"platform": "gp",  "chart_type": "grossing", "genre": "all"},
        ],
    },
    "casual_focus": {
        "name_zh": "休闲游戏专注",
        "name_en": "Casual Focus",
        "description_zh": "休闲 + 益智 + 街机，看轻度游戏市场",
        "charts": [
            {"platform": "ios", "chart_type": "free",     "genre": "all"},
            {"platform": "ios", "chart_type": "grossing", "genre": "all"},
            {"platform": "ios", "chart_type": "free",     "genre": "casual"},
            {"platform": "ios", "chart_type": "free",     "genre": "puzzle"},
            {"platform": "ios", "chart_type": "free",     "genre": "arcade"},
            {"platform": "ios", "chart_type": "grossing", "genre": "casual"},
            {"platform": "ios", "chart_type": "grossing", "genre": "puzzle"},
            {"platform": "gp",  "chart_type": "free",     "genre": "casual"},
            {"platform": "gp",  "chart_type": "free",     "genre": "puzzle"},
            {"platform": "gp",  "chart_type": "grossing", "genre": "casual"},
            {"platform": "gp",  "chart_type": "grossing", "genre": "puzzle"},
        ],
    },
    "midcore": {
        "name_zh": "中重度游戏",
        "name_en": "Midcore / Hardcore",
        "description_zh": "策略 + RPG + 动作，看中重度市场",
        "charts": [
            {"platform": "ios", "chart_type": "free",     "genre": "all"},
            {"platform": "ios", "chart_type": "grossing", "genre": "all"},
            {"platform": "ios", "chart_type": "grossing", "genre": "strategy"},
            {"platform": "ios", "chart_type": "grossing", "genre": "rpg"},
            {"platform": "ios", "chart_type": "free",     "genre": "action"},
            {"platform": "gp",  "chart_type": "grossing", "genre": "strategy"},
            {"platform": "gp",  "chart_type": "grossing", "genre": "rpg"},
            {"platform": "gp",  "chart_type": "free",     "genre": "action"},
        ],
    },
    "full": {
        "name_zh": "完整版 — 全品类 + 热门子品类",
        "name_en": "Full — All + Popular Subcategories",
        "description_zh": "总榜 + 休闲/益智/策略/RPG/动作子品类，覆盖全面",
        "charts": [
            {"platform": "ios", "chart_type": "free",     "genre": "all"},
            {"platform": "ios", "chart_type": "paid",     "genre": "all"},
            {"platform": "ios", "chart_type": "grossing", "genre": "all"},
            {"platform": "ios", "chart_type": "free",     "genre": "casual"},
            {"platform": "ios", "chart_type": "free",     "genre": "puzzle"},
            {"platform": "ios", "chart_type": "grossing", "genre": "casual"},
            {"platform": "ios", "chart_type": "grossing", "genre": "strategy"},
            {"platform": "ios", "chart_type": "grossing", "genre": "rpg"},
            {"platform": "gp",  "chart_type": "free",     "genre": "all"},
            {"platform": "gp",  "chart_type": "paid",     "genre": "all"},
            {"platform": "gp",  "chart_type": "grossing", "genre": "all"},
            {"platform": "gp",  "chart_type": "free",     "genre": "casual"},
            {"platform": "gp",  "chart_type": "free",     "genre": "puzzle"},
            {"platform": "gp",  "chart_type": "grossing", "genre": "strategy"},
            {"platform": "gp",  "chart_type": "grossing", "genre": "rpg"},
        ],
    },
}


def get_preset(name):
    """Get a preset configuration"""
    return PRESETS.get(name)


def list_presets(lang="zh"):
    """List available presets"""
    result = []
    for pid, info in PRESETS.items():
        result.append({
            "id": pid,
            "name": info.get(f"name_{lang}", info["name_en"]),
            "description": info.get(f"description_{lang}", ""),
            "chart_count": len(info["charts"]),
        })
    return result
