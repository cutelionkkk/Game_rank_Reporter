"""
批量玩法分类脚本：
1. 从DB取所有未分类应用
2. iOS用iTunes Lookup API拉 primaryGenreName + description
3. 用Claude批量打标（每批40个）
4. 写入 game_info_cache.json
"""
import json, os, sys, time, re
import urllib.request
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import get_latest_crawl_time, get_rankings_at, get_all_chart_types_at
from game_info import get_game_info, CACHE_FILE, _load_cache, _save_cache

ANTHROPIC_BASE = os.environ.get('ANTHROPIC_BASE_URL', 'https://api.anthropic.com')
ANTHROPIC_TOKEN = os.environ.get('ANTHROPIC_AUTH_TOKEN') or os.environ.get('ANTHROPIC_API_KEY', '')
BATCH_SIZE = 40

SYSTEM_PROMPT = """你是手游玩法分类专家。
输入格式（每行一个应用）: APP_ID|名称|开发商|iOS类型|描述
输出格式：严格JSON数组，每个元素 {"id":"...","gameplay":"玩法标签"}

玩法标签（2~6个中文字，从下列选或自行判断）:
三消消除 三消益智 方块消除 消消乐 泡泡消除 消除类
合并类 合并+叙事
益智解谜 益智休闲 分拣益智 颜色分拣 水排序
箭头解谜 方向解谜 绳子切割
跑酷躲避 跑酷
农场经营 农场建造 城镇建造 模拟经营 餐厅模拟 超市模拟 装修模拟
策略SLG 战争SLG 末日SLG 城堡SLG
RPG 卡牌RPG 放置RPG
放置挂机 点击挂机
大富翁 骰子游戏 派对游戏 社交派对
卡牌游戏 纸牌单机 麻将
射击游戏 射箭游戏
音乐节奏 钢琴节奏
文字益智 填字游戏
赛车竞速
隐藏物品 找不同
换装游戏 美妆游戏
塔防
非游戏（购物/社交/工具等App）

注意：
- 非游戏App（购物、社交媒体、银行、流媒体、导航等）统一标注"非游戏"
- 只输出JSON数组，不要任何解释"""


def itunes_lookup(app_id: str) -> dict:
    try:
        url = f"https://itunes.apple.com/lookup?id={app_id}&country=us"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.loads(r.read())
        results = data.get('results', [])
        if results:
            r = results[0]
            return {
                'genre': r.get('primaryGenreName', ''),
                'description': (r.get('description', '') or '')[:300].replace('\n', ' '),
            }
    except Exception:
        pass
    return {}


def classify_batch(apps_meta: list, retries: int = 3) -> dict:
    lines = []
    for a in apps_meta:
        desc = (a.get('description') or '')[:120].replace('\n', ' ')
        lines.append(f"{a['app_id']}|{a['name']}|{a['dev']}|{a.get('genre','')}|{desc}")

    for attempt in range(retries):
        try:
            resp = requests.post(
                f"{ANTHROPIC_BASE}/v1/messages",
                headers={
                    'anthropic-version': '2023-06-01',
                    'x-api-key': ANTHROPIC_TOKEN,
                    'content-type': 'application/json',
                },
                json={
                    'model': 'claude-opus-4-5',
                    'max_tokens': 2048,
                    'system': SYSTEM_PROMPT,
                    'messages': [{'role': 'user', 'content': '\n'.join(lines)}]
                },
                timeout=60
            )
            text = resp.json()['content'][0]['text'].strip()
            m = re.search(r'\[.*\]', text, re.DOTALL)
            if m:
                data = json.loads(m.group(0))
                return {item['id']: item['gameplay'] for item in data}
            else:
                print(f"  ⚠️ 无法解析JSON: {text[:200]}")
                return {}
        except Exception as e:
            if attempt < retries - 1:
                wait = 3 * (attempt + 1)
                print(f"  ⚠️ 第{attempt+1}次失败，{wait}s后重试: {str(e)[:80]}")
                time.sleep(wait)
            else:
                print(f"  ❌ LLM error (放弃): {str(e)[:80]}")
    return {}


def main():
    # 1. 收集未分类应用
    ct = get_latest_crawl_time()
    charts = get_all_chart_types_at(ct)

    all_apps = {}
    for platform, chart_type in charts:
        apps = get_rankings_at(ct, platform, chart_type)
        for a in apps:
            key = a['app_id']
            if key not in all_apps:
                all_apps[key] = a

    cache = _load_cache()

    unclassified = []
    for app_id, a in all_apps.items():
        info = get_game_info(a['app_name'], a.get('developer', ''), app_id, use_search=False)
        gp = info.get('gameplay', '')
        if not gp or gp == '其他':
            unclassified.append(a)

    print(f"📊 共 {len(all_apps)} 个应用，需分类: {len(unclassified)} 个")

    # 2. 直接用名称+开发商分类（跳过iTunes，网络太慢）
    print("\n🔍 准备分类数据（基于名称+开发商）...")
    enriched = []
    for a in unclassified:
        enriched.append({
            'app_id': a['app_id'],
            'name': a['app_name'],
            'dev': a.get('developer', ''),
            'genre': '',
            'description': '',
        })
    print(f"  ✅ 共 {len(enriched)} 个应用待分类")

    # 3. 批量分类
    print(f"\n🤖 Claude 批量分类（每批 {BATCH_SIZE} 个）...")
    results = {}
    for i in range(0, len(enriched), BATCH_SIZE):
        batch = enriched[i:i+BATCH_SIZE]
        end = min(i + BATCH_SIZE, len(enriched))
        print(f"  批次 {i+1}-{end} / {len(enriched)}...", end=' ', flush=True)
        res = classify_batch(batch)
        results.update(res)
        print(f"✓ ({len(res)} 个)")
        time.sleep(1.5)

    # 4. 写缓存
    updated = 0
    non_game = 0
    for app in unclassified:
        aid = app['app_id']
        gameplay = results.get(aid, '')
        if not gameplay:
            continue
        is_non_game = gameplay == '非游戏'
        final_gameplay = '' if is_non_game else gameplay
        if is_non_game:
            non_game += 1

        cache[aid] = {'gameplay': final_gameplay, 'source': 'llm'}
        name_key = app['app_name'].lower().strip()
        if name_key not in cache:
            cache[name_key] = {'gameplay': final_gameplay, 'source': 'llm'}
        updated += 1

    _save_cache(cache)
    print(f"\n✅ 写入缓存 {updated} 条（其中非游戏 {non_game} 个）")
    print(f"📁 {CACHE_FILE}")

    # 5. 统计
    from collections import Counter
    ctr = Counter()
    for app in unclassified:
        gp = results.get(app['app_id'], '未返回')
        ctr[gp] += 1
    print("\n新分类玩法分布（Top 25）:")
    for tag, cnt in ctr.most_common(25):
        print(f"  {tag}: {cnt}")


if __name__ == '__main__':
    main()
