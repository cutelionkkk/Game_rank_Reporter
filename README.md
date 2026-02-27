<h1 align="center">🎮 Game Rank Reporter</h1>

<p align="center">
  <strong>自动追踪 Google Play & App Store 游戏排行榜，发现市场机会</strong>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge" alt="MIT License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10+-green.svg?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+"></a>
  <a href="https://nodejs.org/"><img src="https://img.shields.io/badge/Node.js-18+-green.svg?style=for-the-badge&logo=node.js&logoColor=white" alt="Node.js 18+"></a>
  <a href="https://github.com/cutelionkkk/Game_rank_Reporter/stargazers"><img src="https://img.shields.io/github/stars/cutelionkkk/Game_rank_Reporter?style=for-the-badge" alt="GitHub Stars"></a>
</p>

<p align="center">
  <a href="#快速上手">快速开始</a> · <a href="#支持的通知渠道">通知渠道</a> · <a href="#分析能力">分析能力</a> · <a href="#设计理念">设计理念</a>
</p>

---

## 为什么需要 Game Rank Reporter？

做游戏行业的竞品分析和市场研究，你需要每天盯着排行榜——但这件事又枯燥又容易遗漏：

- 📊 "昨天哪些游戏排名飙升了？" → **手动翻榜单**，Top 100 得看好几页
- 🆕 "最近有什么新游戏上榜？" → **得记住昨天的排名**，两天没看就忘了
- 📉 "哪些品类在上升？" → **人脑做趋势分析**，主观且容易遗漏
- 🔔 "竞品排名变了我想第一时间知道" → **没有自动提醒**，全靠自己盯
- 📱 "GP 和 iOS 两个平台都要看" → **来回切换**，数据格式还不统一

**每天花 30 分钟翻排行榜？不需要了。**

Game Rank Reporter 每 12 小时自动抓取 6 个榜单（GP + iOS × 免费/付费/畅销），对比历史数据，把**值得关注的变动**推送到你的飞书、钉钉、Discord 或任何你常用的工具。

> ⭐ **Star 这个项目**——我们会持续优化分析算法、接入更多数据源。排行榜数据的价值在于长期积累，越早开始追踪越好。

### ✅ 在你用之前，你可能想知道

| | |
|---|---|
| 💰 **完全免费** | 不需要任何 API Key，不需要付费服务。数据来源全部是公开渠道 |
| 🔄 **全自动运行** | 设置好 cron 后就不用管了，有变动自动推送，没变动不打扰 |
| 📡 **6 个通知渠道** | Discord、Telegram、Slack、飞书、钉钉、企业微信——团队常用的基本都覆盖 |
| 📊 **不只是数据** | 不是简单搬运排名，而是分析变动：飙升、新上榜、品类趋势、持续上升 |
| 💾 **历史可追溯** | SQLite 存储所有历史数据，随时可以回溯任意时间点的排名 |
| 🔌 **可扩展** | 想加新的平台、新的分析维度、新的通知渠道？改一个文件就行 |

---

## 支持的数据源

| 平台 | 免费榜 | 付费榜 | 畅销榜 | 数据量 | 数据来源 |
|------|:------:|:------:|:------:|--------|---------|
| 🍎 **iOS App Store** | ✅ Top 100 | ✅ Top 100 | ✅ Top 100 | 完整 | Apple RSS / iTunes API |
| 📱 **Google Play** | ✅ Top 100 | ✅ Top 100 | ✅ Top 100 | 完整 | google-play-scraper (Node.js) |

> **为什么 GP 用 Node.js？** Google Play 2025 年把 chart 页面改成了纯 SPA，Python 库拿不到数据了。Node.js 的 `google-play-scraper` 直接调用 GP 内部的 batchexecute RPC，稳定可靠。

---

## 分析能力

| 分析维度 | 说明 | 触发条件 |
|---------|------|---------|
| 🔥 **排名飙升** | 排名大幅上升的游戏 | 单次上升 ≥15 名（可配置） |
| 🆕 **新上榜** | 上次不在榜、这次出现了 | 对比前后两次抓取 |
| 🌟 **新游戏** | 上线 30 天内就进入榜单 | 根据发布日期判断 |
| 📉 **排名暴跌** | 排名大幅下降 | 单次下降 ≥15 名 |
| 🚪 **跌出榜单** | 上次在 Top 100，这次没了 | 对比前后两次抓取 |
| 📈 **品类趋势** | 哪些游戏品类在上升/下降 | 7 天窗口内的品类分布变化 |
| 🚀 **持续上升** | 连续多次排名上升的游戏 | 连续 ≥3 次上升 |

---

## 支持的通知渠道

| 渠道 | 推送方式 | 消息格式 | 配置难度 |
|------|---------|---------|---------|
| 🟣 **Discord** | Webhook | Markdown | ⭐ 最简单 |
| 🔵 **Telegram** | Bot API | HTML | ⭐⭐ |
| 🟠 **Slack** | Incoming Webhook | mrkdwn | ⭐ |
| 🔷 **飞书 (Feishu)** | 自定义机器人 | 交互式卡片 | ⭐⭐ |
| 🔷 **钉钉 (DingTalk)** | 自定义机器人 + 加签 | Markdown | ⭐⭐ |
| 🟢 **企业微信 (WeCom)** | 群机器人 | Markdown | ⭐ |

> **不知道怎么配？** 运行 `python setup_wizard.py`，交互式引导你一步步完成。每个渠道的配置步骤也写在下面了。

<details>
<summary><b>Discord — 配置步骤</b></summary>

1. Server Settings → Integrations → Webhooks → New Webhook
2. 选择要发送的频道，复制 Webhook URL
3. `python setup_wizard.py add discord` → 粘贴 URL

</details>

<details>
<summary><b>Telegram — 配置步骤</b></summary>

1. 找 [@BotFather](https://t.me/BotFather) → `/newbot` → 获取 Bot Token
2. 把 Bot 拉进你的群组或频道
3. 获取 Chat ID: 访问 `https://api.telegram.org/bot<TOKEN>/getUpdates`
4. `python setup_wizard.py add telegram` → 输入 Token 和 Chat ID

</details>

<details>
<summary><b>Slack — 配置步骤</b></summary>

1. 打开 [Slack Apps](https://api.slack.com/apps) → Create New App
2. Features → Incoming Webhooks → Activate → Add to Workspace
3. 复制 Webhook URL
4. `python setup_wizard.py add slack`

</details>

<details>
<summary><b>飞书 (Feishu) — 配置步骤</b></summary>

1. 群设置 → 群机器人 → 添加机器人 → 自定义机器人
2. 复制 Webhook URL
3. (可选) 开启签名验证，记录密钥
4. `python setup_wizard.py add feishu`

</details>

<details>
<summary><b>钉钉 (DingTalk) — 配置步骤</b></summary>

1. 群设置 → 智能群助手 → 添加机器人 → 自定义
2. 安全设置选「加签」，记录密钥
3. 复制 Webhook URL
4. `python setup_wizard.py add dingtalk`

</details>

<details>
<summary><b>企业微信 (WeCom) — 配置步骤</b></summary>

1. 群聊 → 右上角 → 群机器人 → 添加
2. 复制 Webhook URL
3. `python setup_wizard.py add wechat`

</details>

---

## 快速上手

### 1. 安装依赖

```bash
# Python 依赖
pip install google-play-scraper requests

# Node.js 依赖 (Google Play 榜单需要)
npm install -g google-play-scraper
```

### 2. 配置通知渠道（可选）

```bash
# 交互式配置向导
python setup_wizard.py

# 或者直接添加
python setup_wizard.py add discord
python setup_wizard.py add feishu

# 测试通知
python setup_wizard.py test discord
```

### 3. 运行

```bash
# 完整流程：抓取 → 分析 → 生成报告 → 推送通知
python run.py

# 也可以分步执行
python run.py --crawl      # 仅抓取数据
python run.py --report     # 从最新数据生成报告
python run.py --notify     # 推送最新报告到已配置渠道
```

### 4. 设置定时任务（推荐每 12 小时）

```bash
# Linux crontab
0 */12 * * * cd /path/to/game-tracker && python3 run.py >> /var/log/game-tracker.log 2>&1
```

<details>
<summary><b>用 OpenClaw 的 cron 系统</b>（点击展开）</summary>

如果你在用 OpenClaw，可以通过内置 cron 设置定时任务，自动推送到你的 Discord/Telegram。

</details>

---

## 报告示例

```
📊 游戏榜单分析报告 — 2026-02-27 12:00 UTC
🇺🇸 美国区 | Top 100

──────────────────────────────
iOS App Store

💰 畅销榜
🔥 飙升最快
  1. ⬆️+45 Royal Kingdom — Simulation — #78→#33
  2. ⬆️+32 Whiteout Survival — Strategy — #55→#23
  3. ⬆️+28 Kingshot — Strategy — #42→#14

🆕 新上榜
  1. #18 SomeNewRPG — RPG 🌟新游戏
  2. #35 AnotherGame — Casual

📈 品类趋势（7日）
  - Strategy: 5→8款 (+3)
  - Simulation: 3→5款 (+2)
  - Casual 持续强势，Top 20 占 6 席

──────────────────────────────
Google Play

💰 畅销榜
🔥 飙升最快
  1. ⬆️+38 MONOPOLY GO! — Board — #45→#7
  ...
```

---

## 设计理念

**Game Rank Reporter 是一个「数据管道 + 分析引擎」，不是 dashboard。**

市面上有很多游戏数据平台（Sensor Tower, data.ai, AppAnnie），但它们要么收费昂贵，要么数据延迟大，要么没有**主动推送**能力。

Game Rank Reporter 的定位不同：

- **不做 dashboard** — 不做可视化界面，专注于「发现变化 → 推送到你面前」
- **不做全量数据** — 只追踪 Top 100，聚焦真正有价值的头部变动
- **不做实时** — 每 12 小时一次，够用且不会被反爬
- **数据归你** — SQLite 本地存储，想怎么查就怎么查

### 🔌 模块化架构

每个模块职责单一，想改哪里改哪里：

```
game-tracker/
├── config.py          → 配置管理        ← 改国家、Top N、阈值
├── settings.json      → 用户配置        ← 自动生成，存渠道密钥
├── crawler.py         → 数据抓取        ← 加新平台？改这里
├── gp_scraper.js      → GP 专用爬虫     ← Node.js bridge
├── database.py        → 数据存储        ← SQLite schema
├── analyzer.py        → 变动分析        ← 加新分析维度？改这里
├── report.py          → 报告生成        ← 改报告格式？改这里
├── notify.py          → 多渠道推送      ← 加新渠道？改这里
├── setup_wizard.py    → 配置向导        ← 交互式设置
└── run.py             → 主入口          ← 编排以上所有模块
```

### 当前技术选型

| 功能 | 选型 | 为什么选它 |
|------|------|-----------|
| iOS 数据 | Apple RSS + iTunes API | 官方数据源，免费，不需要认证 |
| GP 数据 | [google-play-scraper](https://github.com/nicolewhite/google-play-scraper) (Node.js) | 47K+ 下载/周，内置 batchexecute RPC |
| 数据存储 | SQLite | 零配置，单文件，SQL 查询灵活 |
| 通知推送 | Webhook / Bot API | 各平台原生接口，不依赖第三方服务 |

> 📌 不满意某个选型？换掉对应文件就行。iOS 想用 App Store Connect API？改 `crawler.py`。存储想换 PostgreSQL？改 `database.py`。

---

## 配置说明

### settings.json

运行 `setup_wizard.py` 后自动生成，也可以手动编辑：

```json
{
  "country": "us",
  "top_n": 100,
  "charts": ["free", "paid", "grossing"],
  "platforms": ["ios", "gp"],
  "rank_surge_threshold": 15,
  "new_entry_days": 30,
  "report_max_items": 10,
  "notify_channels": ["discord", "feishu"],
  "channel_config": {
    "discord": {
      "webhook_url": "https://discord.com/api/webhooks/...",
      "mention_role": ""
    },
    "feishu": {
      "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/...",
      "secret": ""
    }
  }
}
```

| 配置项 | 说明 | 默认值 |
|-------|------|-------|
| `country` | 目标市场（ISO 国家码） | `us` |
| `top_n` | 追踪前多少名 | `100` |
| `charts` | 追踪哪些榜单 | `["free", "paid", "grossing"]` |
| `platforms` | 追踪哪些平台 | `["ios", "gp"]` |
| `rank_surge_threshold` | 排名变动多少算"飙升" | `15` |
| `new_entry_days` | 上线多少天内算"新游戏" | `30` |
| `report_max_items` | 每个板块最多显示几条 | `10` |

---

## 常见问题 / FAQ

<details>
<summary><strong>Google Play 抓不到数据怎么办？</strong></summary>

GP 的 chart 页面已经改成纯 SPA，Python 的 HTTP 请求拿不到数据。本项目通过 Node.js 的 `google-play-scraper` 库解决，它调用的是 GP 内部的 batchexecute RPC 接口。确保你装了 `npm install -g google-play-scraper`。

</details>

<details>
<summary><strong>iOS 畅销榜为什么用 iTunes RSS？</strong></summary>

Apple 的 RSS v2 API 不提供畅销榜数据（返回 404），但老版的 iTunes RSS（`itunes.apple.com/.../rss/topgrossingapplications`）仍然可用，且提供 Games 分类（genre=6014）的 Top 100 数据。

</details>

<details>
<summary><strong>How to track game rankings automatically?</strong></summary>

Set up a cron job to run `python run.py` every 12 hours. Configure notification channels via `python setup_wizard.py` to receive reports on Discord, Telegram, Slack, Feishu, DingTalk, or WeCom. All data is stored locally in SQLite for historical queries.

</details>

<details>
<summary><strong>服务器在国内，访问 GP/Apple 有问题？</strong></summary>

需要配置代理。在 `settings.json` 同级目录创建 `.env` 文件，设置 `HTTP_PROXY` 和 `HTTPS_PROXY`。Node.js 的 GP 抓取也需要确保代理可用（可通过 `proxychains` 或环境变量）。

</details>

<details>
<summary><strong>Can I track other countries besides the US?</strong></summary>

Yes! Change `country` in `settings.json` to any ISO country code: `jp` (Japan), `kr` (Korea), `cn` (China), `gb` (UK), `de` (Germany), etc. Both GP and iOS support region-specific charts.

</details>

<details>
<summary><strong>数据保存在哪里？怎么查历史数据？</strong></summary>

所有数据保存在 `rankings.db`（SQLite）。你可以用任何 SQLite 工具查询，比如：

```sql
-- 查看某个游戏的排名历史
SELECT crawl_time, rank FROM rankings
WHERE app_name LIKE '%Royal Match%' AND platform='ios' AND chart_type='grossing'
ORDER BY crawl_time;

-- 查看某天的 iOS 畅销榜 Top 10
SELECT rank, app_name, category FROM rankings
WHERE crawl_time LIKE '2026-02-27%' AND platform='ios' AND chart_type='grossing'
ORDER BY rank LIMIT 10;
```

</details>

---

## 使用场景

| 场景 | 怎么用 |
|------|-------|
| 🎯 **竞品监控** | 追踪竞品排名变化，新版本上线后排名是否提升 |
| 💡 **市场机会** | 发现快速上升的品类，找到竞争较少的赛道 |
| 📊 **投资研究** | 监控游戏公司的产品矩阵表现 |
| 🚀 **发行评估** | 观察新游戏上线后的排名走势 |
| 📈 **行业趋势** | 长期积累数据，分析品类和市场周期 |

---

## Roadmap

- [ ] 支持更多地区同时追踪（US + JP + KR）
- [ ] 增加 Web Dashboard（可选）
- [ ] 游戏详情数据采集（评分、评论数、下载量变化）
- [ ] 周报 / 月报汇总模式
- [ ] 自定义监控名单（指定追踪某些游戏）
- [ ] 接入更多数据源（Steam, Nintendo eShop）

---

## 致谢

[google-play-scraper](https://github.com/nicolewhite/google-play-scraper) · [Apple RSS Feed](https://rss.applemarketingtools.com) · [SQLite](https://sqlite.org)

## License

[MIT](LICENSE)
