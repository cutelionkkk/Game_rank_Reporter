# 安装 Game Rank Reporter

需要 Python 3.10+（建议 3.12）及 Node.js 22+。使用项目虚拟环境和本地 Node 依赖，避免全局安装。

```bash
git clone https://github.com/cutelionkkk/Game_rank_Reporter.git
cd Game_rank_Reporter
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm ci
python run.py --serve --open-browser
```

Windows 激活环境使用 `.venv\Scripts\activate`。macOS 安装后可双击 `启动游戏雷达.command`。

在本地网页的“榜单版块”选择商店、国家、榜单、品类及爬升阈值；在“关注公司”搜索并确认开发者账号，保存后点“立即监测”。首次运行只建立历史基线。

通知和定时运行按用户需要配置。网页采集不发送通知。命令行 `python run.py --dry-run` 同样不发送通知；原有 `python run.py` 会使用已有通知设置。不要为了安装验证而发送消息或修改系统计划任务。

旧配置、数据库迁移、来源限制和每日运行示例，见 [完整监测说明](MONITORING.md)。通知渠道仍通过 `python setup_wizard.py` 配置。
