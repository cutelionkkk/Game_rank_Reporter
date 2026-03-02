# Game Rank Reporter — AI Agent 安装指南

## For Humans

复制这句话给你的 AI Agent（Claude Code、OpenClaw、Cursor 等）：

```
帮我安装 Game Rank Reporter：https://raw.githubusercontent.com/cutelionkkk/Game_rank_Reporter/main/docs/install.md
```

---

## For AI Agents

### Goal

帮用户完整安装并配置 Game Rank Reporter，包括：克隆代码、选择追踪榜单、配置通知渠道、设置定时任务。**每一步都必须完成，不得跳过。**

### ⚠️ Boundaries

- **DO NOT** modify system files outside the project directory
- **DO NOT** install packages not listed in this guide
- If something requires elevated permissions, **tell the user** and let them decide

---

### Step 1: Clone and install

```bash
git clone https://github.com/cutelionkkk/Game_rank_Reporter.git
cd Game_rank_Reporter

# Python dependencies
pip install -r requirements.txt

# Node.js dependency (required for Google Play charts)
npm install -g google-play-scraper
```

---

### Step 2: 选择追踪榜单 【必须完成，不得跳过】

安装完成后，**必须询问用户想追踪哪些榜单**，不得使用默认值直接跳过。

先向用户说明可选项：

> "Game Rank Reporter 安装好了！现在需要配置你想追踪的榜单。
>
> 有以下几个预设方案可以选择：
> - **游戏全榜**：iOS + Google Play 免费榜/畅销榜（最全面）
> - **iOS 精选**：iOS 免费榜 + 畅销榜（仅苹果）
> - **GP 精选**：Google Play 免费榜 + 畅销榜（仅安卓）
> - **休闲游戏**：iOS + GP 休闲品类榜
> - **益智游戏**：iOS + GP 益智品类榜
> - **自定义**：手动选择平台、榜单类型、游戏品类
>
> 你想选哪个方案？或者告诉我你关注的方向，我来推荐。"

根据用户回答，运行配置命令：

```bash
# 使用预设（例如 full / ios_only / gp_only / casual / puzzle）
python setup_wizard.py charts
# 或直接指定预设
python setup_wizard.py presets   # 查看所有预设
```

配置完成后，确认并输出榜单清单给用户确认。

---

### Step 3: 配置通知渠道 【必须完成，不得跳过】

**必须询问用户想通过哪个渠道接收报告**，不得跳过此步骤。

向用户提问：

> "报告生成后发到哪里？支持以下渠道，请选一个：
> - **Telegram**：需要一个 Bot Token 和你的 Chat ID（最推荐，设置简单）
> - **Discord**：需要一个 Webhook URL
> - **飞书**：需要群机器人 Webhook URL
> - **钉钉**：需要群机器人 Webhook URL
> - **Slack**：需要 Incoming Webhook URL
> - **企业微信**：需要群机器人 Webhook URL
>
> 你选哪个？"

#### Telegram（最常用，详细引导）

如果用户选择 Telegram：

1. 引导用户创建 Bot：
   > "请打开 Telegram，搜索 @BotFather，发送 /newbot，按提示创建一个 Bot，完成后把 Token 发给我（格式类似 `123456:ABC-xxx`）。"

2. 获取 Chat ID：
   > "创建好后，请去找你的 Bot（直接搜索你刚起的用户名），发一条任意消息，然后告诉我，我来查你的 Chat ID。"

3. 配置并测试：
   ```bash
   python setup_wizard.py add telegram
   python setup_wizard.py test telegram
   ```

#### Discord

引导用户在频道设置中创建 Webhook，然后：
```bash
python setup_wizard.py add discord
python setup_wizard.py test discord
```

#### 其他渠道

```bash
python setup_wizard.py add <channel>   # feishu / dingtalk / slack / wechat
python setup_wizard.py test <channel>
```

测试通过后，向用户确认收到了测试消息。

---

### Step 4: 运行首次完整测试

```bash
python run.py
```

这会执行：抓取 → 分析 → 生成报告 → 发送通知。

把报告结果展示给用户看，确认格式和内容符合预期。

---

### Step 5: 设置定时任务 【必须询问用户】

询问用户：

> "要不要设置定时自动抓取？比如每天早上 9 点自动抓取并推送报告，有排名变动时你第一时间知道。
> 你希望多久抓取一次？（推荐：每 12 小时 / 每天一次）"

根据用户回答设置：

**如果使用 OpenClaw**，创建 cron job：
- 时间按用户要求设置
- payload: `cd /path/to/Game_rank_Reporter && python3 run.py`

**如果使用系统 cron**：

```bash
crontab -e
# 每天 9:00（北京时间，UTC+8 = UTC 01:00）
0 1 * * * cd /path/to/Game_rank_Reporter && python3 run.py >> /var/log/game-tracker.log 2>&1
```

设置完成后告知用户下次自动推送的时间。

---

### Step 6: AI 分析（可选，主动提及）

> "还有一个可选功能：可以导出结构化数据，交给 AI 做深度市场分析（品类趋势、竞品对比等）。需要的时候运行：`python run.py --export-analysis`，生成的 analysis_data.json 可以直接喂给 GPT/Claude 分析。"

---

## Quick Reference

| Command | What it does |
|---------|-------------|
| `python run.py` | Full run: crawl + analyze + report + notify |
| `python run.py --crawl` | Crawl only |
| `python run.py --report` | Generate report from latest data |
| `python run.py --notify` | Send latest report to channels |
| `python run.py --export-analysis` | Export structured data for AI analysis |
| `python setup_wizard.py` | Interactive full setup |
| `python setup_wizard.py charts` | Configure tracked charts |
| `python setup_wizard.py add <channel>` | Add a notification channel |
| `python setup_wizard.py test <channel>` | Test a channel |
| `python setup_wizard.py status` | Show current config |
| `python setup_wizard.py presets` | List available chart presets |
