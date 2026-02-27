# 🎮 Game Rank Reporter

Automated game ranking tracker and analyzer for **Google Play** and **iOS App Store**.

Crawls top charts every 12 hours, stores historical data, detects ranking changes, and generates analysis reports.

## Features

- 📊 **Dual Platform** — Google Play + iOS App Store
- 📈 **Three Charts** — Free, Paid, Top Grossing
- 🇺🇸 **US Market** — Focused on the US region (configurable)
- 🔍 **Change Detection** — Surges, drops, new entries, exits
- 📉 **Trend Analysis** — Category trends, consecutive risers
- 🤖 **Automated Reports** — Cron-ready, Discord-friendly output
- 💾 **SQLite Storage** — Lightweight, zero-config database

## Quick Start

### Prerequisites

```bash
pip install google-play-scraper requests
```

### Run

```bash
python run.py
```

This will:
1. Crawl all 6 charts (iOS × 3 + GP × 3)
2. Store results in `rankings.db`
3. Compare with previous crawl
4. Generate an analysis report

### Output Example

```
📊 游戏榜单分析报告 — 2026-02-27 12:00 UTC
🇺🇸 美国区 | Top 100

iOS App Store
💰 畅销榜
🔥 飙升最快
  1. ⬆️+45 某某大冒险 — Puzzle — #78→#33
  2. ⬆️+32 战争前线 — Strategy — #55→#23

🆕 新上榜
  1. #18 幻想传说 — RPG 🌟新游戏
```

## Architecture

```
game-tracker/
├── config.py      # Configuration (country, top N, thresholds)
├── crawler.py     # Google Play & iOS crawlers
├── database.py    # SQLite schema & queries
├── analyzer.py    # Ranking change detection & trend analysis
├── report.py      # Discord-friendly report generator
├── run.py         # Main entry point
└── README.md
```

## Data Sources

| Platform | Method | Coverage |
|----------|--------|----------|
| iOS Free | Apple RSS v2 API | Top 100 |
| iOS Paid | Apple RSS v2 API | Top 100 |
| iOS Grossing | iTunes RSS (genre=Games) | Top 100 |
| GP Free | Web scrape + `google-play-scraper` | ~80 games |
| GP Paid | Web scrape (limited by GP) | varies |
| GP Grossing | Web scrape (limited by GP) | varies |

> **Note:** Google Play has restricted public access to chart data. GP coverage may be less than 100 depending on what Google returns.

## Configuration

Edit `config.py`:

```python
COUNTRY = "us"          # Target market
TOP_N = 100             # How many to track
RANK_SURGE_THRESHOLD = 15   # Rank jump to flag as "surge"
NEW_ENTRY_DAYS = 30     # Games released within N days = "new"
```

## Automation

### With OpenClaw (cron)

Set up a cron job to run every 12 hours:

```bash
# The cron job runs: python /path/to/game-tracker/run.py
# and sends the report to your configured channel
```

### Standalone

```bash
# Add to system crontab
0 */12 * * * cd /path/to/game-tracker && python3 run.py >> /var/log/game-tracker.log 2>&1
```

## Analysis Capabilities

- **Rank Surges** — Games that jumped ≥15 positions
- **New Entries** — Games that weren't in the chart last crawl
- **New Games** — Recently released games that entered the chart
- **Rank Drops** — Games that fell ≥15 positions
- **Chart Exits** — Games that dropped out of Top 100
- **Category Trends** — Which genres are gaining/losing representation
- **Consecutive Risers** — Games rising steadily over multiple crawls

## Use Cases

- 🎯 **Competitive Analysis** — Track competitor game performance
- 💡 **Market Opportunity** — Spot rising genres and underserved categories
- 📊 **Investment Research** — Monitor publisher portfolio performance
- 🚀 **Launch Tracking** — Watch new game launches and their trajectory

## License

MIT
