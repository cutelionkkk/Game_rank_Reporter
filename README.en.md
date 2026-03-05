<h1 align="center">🎮 Game Rank Reporter</h1>

<p align="center">
  <strong>Automatically track Google Play & App Store game rankings to discover market opportunities</strong>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge" alt="MIT License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10+-green.svg?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+"></a>
  <a href="https://nodejs.org/"><img src="https://img.shields.io/badge/Node.js-18+-green.svg?style=for-the-badge&logo=node.js&logoColor=white" alt="Node.js 18+"></a>
  <a href="https://github.com/cutelionkkk/Game_rank_Reporter/stargazers"><img src="https://img.shields.io/github/stars/cutelionkkk/Game_rank_Reporter?style=for-the-badge" alt="GitHub Stars"></a>
</p>

<p align="center">
  <a href="README.md">中文</a> | <b>English</b>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> · <a href="#ai-agent-install">AI Agent Install</a> · <a href="#notification-channels">Notifications</a> · <a href="#analysis">Analysis</a> · <a href="#design">Design</a>
</p>

---

## Why Game Rank Reporter?

Tracking app store rankings manually is tedious — you have to check multiple charts, remember yesterday's positions, and spot trends by hand.

**Game Rank Reporter automates all of this.** It fetches 6 charts (GP + iOS × Free/Paid/Grossing) every 12 hours, compares against history, and pushes **meaningful changes** to Feishu, Discord, Telegram, or any tool you already use.

### ✅ Things you might want to know

| | |
|---|---|
| 💰 **Completely free** | No API keys needed. All data comes from public sources |
| 🔄 **Fully automated** | Set up a cron job and forget it. Alerts only when something moves |
| 📡 **6 notification channels** | Discord, Telegram, Slack, Feishu, DingTalk, WeCom |
| 📊 **Analysis, not just data** | Detects surges, new entries, category trends, sustained risers |
| 💾 **Full history** | SQLite stores all snapshots — query any past date |
| 🔌 **Extensible** | One file change to add a new platform, analysis dimension, or channel |

---

## Data Sources

| Platform | Free | Paid | Grossing | Source |
|----------|:----:|:----:|:--------:|--------|
| 🍎 **iOS App Store** | ✅ Top 100 | ✅ Top 100 | ✅ Top 100 | Apple RSS / iTunes API |
| 📱 **Google Play** | ✅ Top 100 | ✅ Top 100 | ✅ Top 100 | google-play-scraper (Node.js) |

> **Why Node.js for GP?** Google Play switched to a pure SPA in 2025. The Node.js `google-play-scraper` calls GP's internal batchexecute RPC directly — reliable and fast.

---

## Analysis

> ⚠️ **No analysis on the first run!** Change detection requires at least two crawls for comparison. The first run saves a snapshot; full analysis starts from the second run onward. Recommend running every 12 hours via cron.

| Signal | Description | Trigger |
|--------|-------------|---------|
| 🔥 **Rank Surge** | Game climbed significantly | ≥15 positions up (configurable) |
| 🆕 **New Entry** | Not in last snapshot, now present | Per-crawl comparison |
| 🌟 **New Release** | In chart within 30 days of launch | Based on release date |
| 📉 **Rank Drop** | Game fell significantly | ≥15 positions down |
| 🚪 **Fell Off** | Was in Top 100, now gone | Per-crawl comparison |
| 📈 **Category Trend** | Genre rising or falling | 7-day window |
| 🚀 **Sustained Riser** | Climbing multiple consecutive runs | ≥3 consecutive gains |

---

## Notification Channels

| Channel | Method | Difficulty |
|---------|--------|-----------|
| 🟣 **Discord** | Webhook | ⭐ Easiest |
| 🔵 **Telegram** | Bot API | ⭐⭐ |
| 🟠 **Slack** | Incoming Webhook | ⭐ |
| 🔷 **Feishu** | Custom Bot | ⭐⭐ |
| 🔷 **DingTalk** | Custom Bot + HMAC | ⭐⭐ |
| 🟢 **WeCom** | Group Bot | ⭐ |

> **Not sure how to configure?** Run `python setup_wizard.py` for an interactive step-by-step guide.

---

## AI Agent Install

Paste this into your AI Agent (Claude Code, OpenClaw, Cursor, Windsurf, etc.):

```
Help me install Game Rank Reporter: https://raw.githubusercontent.com/cutelionkkk/Game_rank_Reporter/main/docs/install.md
```

The agent will: clone the repo, install dependencies, run the first crawl, and configure your notification channels.

---

## Quick Start (Manual)

### 1. Install dependencies

```bash
# Python
pip install google-play-scraper requests

# Node.js (required for Google Play)
npm install -g google-play-scraper
```

### 2. Configure notifications (optional)

```bash
python setup_wizard.py
# or add a specific channel
python setup_wizard.py add discord
```

### 3. Run

```bash
# Full pipeline: crawl → analyze → report → notify
python run.py

# Or step by step
python run.py --crawl      # crawl only
python run.py --report     # generate report from latest data
python run.py --notify     # push latest report
```

### 4. Set up cron (recommended every 12h)

```bash
0 */12 * * * cd /path/to/game-tracker && python3 run.py >> /var/log/game-tracker.log 2>&1
```

---

## Sample Report

```
💰 iOS Grossing Top 10 — 2026-02-27 12:00 UTC

#1 Royal Match (Puzzle)  ⬆️+3
   Dream Games
#2 Gossip Harbor (Merge+Story)
   Microfun Limited
#4 Royal Kingdom (Puzzle)  🆕
   Dream Games

📊 This run:
  🔥 Surging: Royal Kingdom #15→#4 (+3 others)
  🆕 New entries: Royal Kingdom (#4), Pixel Flow! (#7)
  🚪 Fell off: Block Puzzle Master, Tile Blast
```

---

## Architecture

```
game-tracker/
├── config.py          → configuration
├── settings.json      → user settings (auto-generated)
├── crawler.py         → data crawling
├── gp_scraper.js      → Google Play bridge (Node.js)
├── database.py        → SQLite storage
├── analyzer.py        → change detection
├── report.py          → report formatting
├── notify.py          → multi-channel push
├── setup_wizard.py    → interactive setup
└── run.py             → main entrypoint
```

---

## Configuration

Key settings in `settings.json`:

| Key | Description | Default |
|-----|-------------|---------|
| `country` | Target market (ISO code) | `us` |
| `top_n` | Track top N games | `100` |
| `charts` | Which charts to track | `["free","paid","grossing"]` |
| `rank_surge_threshold` | Min positions to count as a surge | `15` |
| `new_entry_days` | Days since launch to flag as "new game" | `30` |

---

## Roadmap

- [x] Per-chart separate messages ✅
- [x] Game genre classification (rules + AI enrichment) ✅
- [ ] Multi-region tracking (US + JP + KR simultaneously)
- [ ] Web Dashboard (optional)
- [ ] Game detail tracking (ratings, review count, downloads)
- [ ] Weekly / monthly summary reports
- [ ] Custom watchlist (track specific games)
- [ ] More data sources (Steam, Nintendo eShop)

---

## Credits

[google-play-scraper](https://github.com/nicolewhite/google-play-scraper) · [Apple RSS Feed](https://rss.applemarketingtools.com) · [SQLite](https://sqlite.org)

## License

[MIT](LICENSE)
