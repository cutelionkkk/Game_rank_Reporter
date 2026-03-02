"""Game info lookup — gameplay type via web_search + local cache"""

import json
import os
import re
import time

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'game_info_cache.json')

# ----------------------------------------------------------------
# Hardcoded well-known games (fast path, no search needed)
# Format: app_id or lowercased app_name → {gameplay, genre_tag}
# ----------------------------------------------------------------
KNOWN_GAMES = {
    # Puzzle / Match-3
    "royal match":         {"gameplay": "三消益智", "genre_tag": "Match-3"},
    "royal kingdom":       {"gameplay": "三消益智", "genre_tag": "Match-3"},
    "candy crush saga":    {"gameplay": "三消消除", "genre_tag": "Match-3"},
    "candy crush soda saga": {"gameplay": "三消消除", "genre_tag": "Match-3"},
    "toon blast":          {"gameplay": "消方块益智", "genre_tag": "Blast Puzzle"},
    "toy blast":           {"gameplay": "消方块益智", "genre_tag": "Blast Puzzle"},
    "block blast":         {"gameplay": "方块消除", "genre_tag": "Block Puzzle"},
    "block blast!":        {"gameplay": "方块消除", "genre_tag": "Block Puzzle"},
    "block\xa0blast！":    {"gameplay": "方块消除", "genre_tag": "Block Puzzle"},
    "pixel flow":          {"gameplay": "连线填色益智", "genre_tag": "Flow Puzzle"},
    "pixel flow!":         {"gameplay": "连线填色益智", "genre_tag": "Flow Puzzle"},
    "magic sort":          {"gameplay": "颜色分拣益智", "genre_tag": "Sort Puzzle"},
    "magic sort!":         {"gameplay": "颜色分拣益智", "genre_tag": "Sort Puzzle"},
    "tile explorer":       {"gameplay": "三张消除（图块连消）", "genre_tag": "Tile Match"},
    "game is hard":        {"gameplay": "创意休闲益智", "genre_tag": "Casual Puzzle"},
    "arrows – puzzle escape": {"gameplay": "箭头方向解谜", "genre_tag": "Puzzle"},
    "arrow out":           {"gameplay": "箭头方向解谜", "genre_tag": "Puzzle"},
    "block crush":         {"gameplay": "方块消除", "genre_tag": "Block Puzzle"},

    # Merge
    "gossip harbor":       {"gameplay": "合并+叙事", "genre_tag": "Merge"},
    "gossip harbor®: merge & story": {"gameplay": "合并+叙事", "genre_tag": "Merge"},
    "merge dragons":       {"gameplay": "龙合并养成", "genre_tag": "Merge"},
    "merge dragons!":      {"gameplay": "龙合并养成", "genre_tag": "Merge"},

    # Strategy / SLG
    "last war:survival":   {"gameplay": "末日战争SLG", "genre_tag": "SLG"},
    "last war: survival":  {"gameplay": "末日战争SLG", "genre_tag": "SLG"},
    "kingshot":            {"gameplay": "城堡战争SLG", "genre_tag": "SLG"},
    "rise of kingdoms":    {"gameplay": "文明建造SLG", "genre_tag": "SLG"},
    "whiteout survival":   {"gameplay": "雪地生存SLG", "genre_tag": "SLG"},

    # Casual / Social
    "monopoly go":         {"gameplay": "大富翁骰子社交", "genre_tag": "Board"},
    "monopoly go!":        {"gameplay": "大富翁骰子社交", "genre_tag": "Board"},
    "coin master":         {"gameplay": "老虎机+建造", "genre_tag": "Casual"},
    "township":            {"gameplay": "农场城镇建造", "genre_tag": "Farming"},
    "gardenscapes":        {"gameplay": "三消+花园装修", "genre_tag": "Match-3 + Decor"},
    "homescapes":          {"gameplay": "三消+家居装修", "genre_tag": "Match-3 + Decor"},
    "hay day":             {"gameplay": "农场经营模拟", "genre_tag": "Farming"},
    "subway surfers":      {"gameplay": "跑酷躲避", "genre_tag": "Endless Runner"},
    "subway surfers city": {"gameplay": "跑酷躲避", "genre_tag": "Endless Runner"},

    # RPG / Battle
    "pokémon go":          {"gameplay": "AR 捕捉宝可梦", "genre_tag": "AR RPG"},
    "pokemon go":          {"gameplay": "AR 捕捉宝可梦", "genre_tag": "AR RPG"},

    # Simulation
    "my supermarket simulator 3d®": {"gameplay": "超市经营模拟", "genre_tag": "Simulation"},

    # Hyper/Casual
    "water match":         {"gameplay": "水颜色分类", "genre_tag": "Sort Puzzle"},
    "water match™":        {"gameplay": "水颜色分类", "genre_tag": "Sort Puzzle"},
    "arrowscapes":         {"gameplay": "箭头路径解谜", "genre_tag": "Puzzle"},
    "arrowscapes™ - arrows puzzle": {"gameplay": "箭头路径解谜", "genre_tag": "Puzzle"},
    "3d bubble shoot":     {"gameplay": "3D泡泡射击消除", "genre_tag": "Bubble Shooter"},
    "yahtzee® with buddies dice": {"gameplay": "骰子益智社交", "genre_tag": "Dice"},

    # Card / Party
    "uno!™":               {"gameplay": "UNO牌类多人对战", "genre_tag": "Card"},
    "uno!":                {"gameplay": "UNO牌类多人对战", "genre_tag": "Card"},

    # Hybrid
    "heartopia":           {"gameplay": "农场+恋爱模拟", "genre_tag": "Simulation"},
    "imposter game":       {"gameplay": "狼人杀派对", "genre_tag": "Party"},
}

# ----------------------------------------------------------------
# Rule-based fallback (keyword matching)
# ----------------------------------------------------------------
KEYWORD_RULES = [
    (r'\bblast\b',           "消除类"),
    (r'\bcrush\b',           "消除类"),
    (r'\bbubble\b',          "泡泡消除"),
    (r'\bmatch\b',           "消消乐"),
    (r'\bmerge\b',           "合并类"),
    (r'\btower.?defense\b',  "塔防"),
    (r'\bidle\b|\bclicker\b',"放置挂机"),
    (r'\bsurvival\b',        "生存SLG"),
    (r'\bsurf(er|ers)\b',    "跑酷"),
    (r'\bpuzzle\b',          "益智解谜"),
    (r'\bsort\b',            "分拣益智"),
    (r'\bfarm\b|\bagri\b',   "农场经营"),
    (r'\bsimulat\b',         "模拟经营"),
    (r'\brpg\b',             "RPG"),
    (r'\bslg\b|\bstrateg\b', "策略SLG"),
    (r'\brace\b|\bracing\b', "赛车竞速"),
    (r'\bshoot(er|ing)?\b',  "射击"),
    (r'\bword\b|\bcrossword\b', "文字益智"),
    (r'\bsolitaire\b',       "纸牌单机"),
    (r'\bchess\b|\bboard\b', "棋盘"),
    (r'\bblock\b',           "方块益智"),
    (r'\bflow\b|\bcolor\b',  "连线/填色"),
    (r'\bcraft\b|\bmine\b',  "沙盒建造"),
    (r'\bdraw\b',            "绘画益智"),
]


def _rule_based_gameplay(app_name: str) -> str | None:
    """Quick keyword match — return gameplay tag or None"""
    name_lower = app_name.lower()
    for pattern, tag in KEYWORD_RULES:
        if re.search(pattern, name_lower):
            return tag
    return None


def _load_cache() -> dict:
    if os.path.exists(CACHE_FILE):
        try:
            return json.load(open(CACHE_FILE, 'r', encoding='utf-8'))
        except Exception:
            return {}
    return {}


def _save_cache(cache: dict):
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def _search_game_info(app_name: str, developer: str = '') -> dict | None:
    """Search web for game info. Returns dict with 'gameplay' key or None."""
    try:
        from web_search_wrapper import web_search
    except ImportError:
        return None

    query = f"{app_name} mobile game gameplay type"
    if developer:
        query += f" {developer}"

    try:
        results = web_search(query, count=3)
        if not results:
            return None

        # Combine snippets
        text = ' '.join(r.get('snippet', '') + ' ' + r.get('title', '') for r in results)
        text_lower = text.lower()

        # Try to extract gameplay type from snippets
        for pattern, tag in KEYWORD_RULES:
            if re.search(pattern, text_lower):
                return {"gameplay": tag, "source": "web"}

        # Check for explicit type mentions
        type_patterns = [
            (r'match.?3', "三消"),
            (r'三消', "三消"),
            (r'merge game', "合并类"),
            (r'idle game', "放置挂机"),
            (r'strategy game', "策略"),
            (r'simulation', "模拟经营"),
            (r'role.?playing', "RPG"),
            (r'puzzle game', "益智解谜"),
            (r'casual game', "休闲"),
            (r'card game', "卡牌"),
            (r'runner', "跑酷"),
            (r'shooter', "射击"),
        ]
        for pattern, tag in type_patterns:
            if re.search(pattern, text_lower):
                return {"gameplay": tag, "source": "web"}

    except Exception:
        pass

    return None


def get_game_info(app_name: str, developer: str = '', app_id: str = '',
                  use_search: bool = True, search_delay: float = 0.5) -> dict:
    """
    Get game info (gameplay type, genre tag) for an app.
    Priority: hardcoded → cache → rule-based → web_search → unknown

    Returns dict: {"gameplay": str, "genre_tag": str, "source": str}
    """
    name_key = app_name.lower().strip()

    # 1. Hardcoded known games
    if name_key in KNOWN_GAMES:
        return {**KNOWN_GAMES[name_key], "source": "known"}

    # 2. Local cache
    cache = _load_cache()
    cache_key = f"{app_id or name_key}"
    if cache_key in cache:
        return {**cache[cache_key], "source": "cache"}

    # 3. Rule-based keyword matching
    rule_result = _rule_based_gameplay(app_name)

    # 4. Web search (only if rule-based didn't find anything definitive)
    search_result = None
    if use_search:
        try:
            time.sleep(search_delay)
            search_result = _search_game_info(app_name, developer)
        except Exception:
            pass

    # Combine: prefer search if it found something, else use rule
    gameplay = None
    source = "unknown"
    if search_result and search_result.get("gameplay"):
        gameplay = search_result["gameplay"]
        source = "web"
    elif rule_result:
        gameplay = rule_result
        source = "rule"

    result = {
        "gameplay": gameplay or "",
        "genre_tag": "",
        "source": source,
    }

    # Cache the result (even if empty, to avoid re-searching)
    if gameplay:
        cache[cache_key] = {"gameplay": gameplay, "genre_tag": result["genre_tag"]}
        _save_cache(cache)

    return result


def prefetch_game_info(apps: list, use_search: bool = True) -> dict:
    """
    Prefetch game info for a list of apps (deduplicated).
    Returns dict: app_id/name → game_info dict
    """
    results = {}
    seen = set()

    for app in apps:
        app_id = app.get('app_id', '')
        app_name = app.get('app_name', '')
        key = app_id or app_name.lower()

        if key in seen:
            continue
        seen.add(key)

        info = get_game_info(
            app_name=app_name,
            developer=app.get('developer', ''),
            app_id=app_id,
            use_search=use_search,
        )
        results[key] = info

    return results
