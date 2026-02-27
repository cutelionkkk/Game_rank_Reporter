# Game Rank Reporter — AI Agent 安装指南

## For Humans

复制这句话给你的 AI Agent（Claude Code、OpenClaw、Cursor 等）：

```
帮我安装 Game Rank Reporter：https://raw.githubusercontent.com/cutelionkkk/Game_rank_Reporter/main/docs/install.md
```

## For AI Agents

### Goal

Install Game Rank Reporter so your user can automatically track Google Play and iOS App Store game rankings, detect changes, and receive analysis reports via their preferred messaging platform.

### ⚠️ Boundaries

- **DO NOT** modify system files outside the project directory
- **DO NOT** install packages not listed in this guide
- If something requires elevated permissions, **tell the user** and let them decide

### Step 1: Clone and install

```bash
git clone https://github.com/cutelionkkk/Game_rank_Reporter.git
cd Game_rank_Reporter

# Python dependencies
pip install -r requirements.txt

# Node.js dependency (required for Google Play charts)
npm install -g google-play-scraper
```

### Step 2: Verify installation

```bash
python run.py --crawl
```

This should crawl all 6 charts (iOS × 3 + GP × 3) and store results in `rankings.db`.

Expected output:
- iOS Free: ~100 games
- iOS Paid: ~100 games  
- iOS Grossing: ~100 games
- GP Free: ~100 games
- GP Paid: ~100 games
- GP Grossing: ~100 games

If any chart fails, check:
- Internet connectivity (some regions need proxy for Apple/Google)
- Node.js is installed (`node --version`)
- `google-play-scraper` npm package is installed (`npm list -g google-play-scraper`)

### Step 3: Configure notification channels (optional)

Ask the user which channels they want to receive reports on:

> "Game Rank Reporter 安装好了。你想通过什么渠道接收报告？支持：Discord、Telegram、Slack、飞书、钉钉、企业微信。"

Then configure based on their choice:

```bash
# Interactive wizard
python setup_wizard.py

# Or directly
python setup_wizard.py add discord
python setup_wizard.py add feishu
python setup_wizard.py add dingtalk
# etc.
```

Test the channel:
```bash
python setup_wizard.py test <channel_name>
```

### Step 4: Run a full test

```bash
python run.py
```

This runs: crawl → analyze → report → notify.

Show the report to the user for confirmation.

### Step 5: Set up automated scheduling

Ask the user:

> "要不要设置每 12 小时自动抓取并推送报告？"

**If using OpenClaw**, create a cron job:

```
运行 cd /path/to/Game_rank_Reporter && python3 run.py
如果报告生成成功，把报告内容发给用户。
如果有错误，告诉用户哪个榜单抓取失败了。
```

**If using system cron:**

```bash
crontab -e
# Add:
0 */12 * * * cd /path/to/Game_rank_Reporter && python3 run.py >> /var/log/game-tracker.log 2>&1
```

### Step 6: AI-Powered Analysis (optional)

Game Rank Reporter can export structured data for AI analysis. After crawling:

```bash
python run.py --export-analysis
```

This generates `analysis_data.json` — a structured dataset you can feed into your analysis workflow. See `docs/ai_analysis_guide.md` for the full prompt template and analysis methodology.

---

## Quick Reference

| Command | What it does |
|---------|-------------|
| `python run.py` | Full run: crawl + analyze + report + notify |
| `python run.py --crawl` | Crawl only |
| `python run.py --report` | Generate report from latest data |
| `python run.py --notify` | Send latest report to channels |
| `python run.py --export-analysis` | Export structured data for AI analysis |
| `python setup_wizard.py` | Interactive channel setup |
| `python setup_wizard.py add <channel>` | Add a notification channel |
| `python setup_wizard.py test <channel>` | Test a channel |
| `python setup_wizard.py status` | Show current config |
