# 每天 9 点，分别发送飞书私聊

GitHub Actions 在北京时间每天 09:00 启动采集，不依赖本地电脑开机。采集完成后将榜单爬升和公司新游汇总给每位接收人；过长时分段发送。首次采集只建立基线，新增关注的公司和地区也先建立基线。

日报和试推均使用飞书卡片：蓝色标题栏、分栏目的标题与分隔线、绿色上涨数字。所有有有效商店 ID 的游戏名称均可直接点击，打开相应国家的 App Store 或 Google Play 产品页；包括爬升、新上榜、公司新游、首次发现和无历史时的排名快照。链接来自采集到的产品 ID，不通过名称搜索匹配。

卡片按完整内容块分页，保留产品名称和链接；按序列化后的实际请求大小控制在 28 KB 内。历史富文本投递记录自动保留原消息类型，重试不会把旧消息改成另一种内容或重复发送。卡片结构参考[飞书卡片 JSON 2.0](https://open.feishu.cn/document/feishu-cards/card-json-v2-structure)，需要支持该格式的飞书客户端。

## 应用与接收人

1. 在[飞书开放平台](https://open.feishu.cn/app)创建企业自建应用，添加“机器人”能力。
2. 添加应用身份权限 `im:message:send_as_bot`。无需读取聊天记录或云文档权限。
3. 将应用可用范围设为实际接收人，创建版本并发布；企业可能要求管理员审批。
4. 核对接收人的企业邮箱，或使用**这份应用对应的** `open_id`。不同应用的 `open_id` 不能直接互用。

群自定义机器人 Webhook 只适用于群通知；单独私聊使用企业自建应用的机器人。

## GitHub 配置

将工作流合入默认分支。在仓库 Settings → Secrets and variables → Actions 中添加以下 Repository secrets：

| 名称 | 内容 |
| --- | --- |
| `FEISHU_APP_ID` | 专用日报应用的 App ID |
| `FEISHU_APP_SECRET` | 同一应用的 App Secret |
| `FEISHU_RECIPIENTS` | 接收人 JSON 数组，示例见下方 |
| `MONITOR_SETTINGS_JSON` | 本地网页选择的监测配置，点击“同步每天推送”更新 |
| `MONITOR_STATE_KEY` | 32 字节随机密钥的 Base64 编码，用于加密历史；必须备份，不能随意重置 |

另添加 Repository variable `MONITOR_ENABLED`，值设为 `true`。设为 `false` 可停用推送。

接收人示例（不要把真实接收人提交到公开仓库）：

```json
[
  {"type": "email", "id": "reader@example.com"},
  {"type": "email", "id": "colleague@example.com"}
]
```

生成历史密钥时将输出直接送入秘密管理工具，不要放到聊天、截图、代码或公开日志。初始化后需保留一份私密备份。

完成配置后，在 Actions → Daily game radar → Run workflow 中首次勾选 `initialize_history`。勾选 `collect_only` 可仅采集和保存历史，不发消息。之后重跑不需要勾选首次初始化。已有历史时，即使勾选初始化也会优先恢复原有历史。

## 调整日常监测范围

打开本地网页，选择商店、国家、榜单、品类和公司名单后，点击**同步每天推送**。该按钮保存本地设置，并通过已登录的 GitHub CLI 更新当前项目 origin 仓库的 `MONITOR_SETTINGS_JSON`。它不更改接收人、应用密钥或启停状态。

只点“保存设置”会保存到本地；只点“立即监测”会进行本地采集，不发送消息。云端与本地各自保留历史，网页当前展示的是本地运行结果。云端日报在飞书查看，执行结果在 GitHub Actions 查看。

## 历史和失败处理

- 历史排名、公司发现和投递记录在离开执行机器前以 AES-256-GCM 加密，保存为 `game-radar-state` artifact；公开仓库不上传明文数据库、接收人或报告。
- 每天恢复最新一份历史，保留 90 天排名；公司已知产品和首次发现记录持续保留，避免把老游戏反复当新游。
- 同一北京时间日期、应用和接收人使用固定的投递记录；正常重跑会跳过已成功发送的部分，只重试失败部分。当天重跑沿用第一次生成的报告内容，避免同一天两份不一致的日报。
- 飞书返回 HTTP 200 但业务错误时会判定失败。某个接收人失败不阻止其他接收人投递；工作流仍报错并保存已送达记录。
- 历史缺失、过期、解密失败会停止运行，不会默默丢失历史并从头发送。首次初始化选项仅允许在完全没有历史 artifact 时建立新基线。
- GitHub artifact 默认保留期在本工作流设为 90 天（受仓库/组织上限约束）；长时间停用前应备份最近的加密历史和密钥。强制取消进程或 artifact 上传失败可能丢失本次投递记录，应核对飞书消息后再重跑。

GitHub 的定时任务可能排队，09:00 是计划启动时间，不保证消息准点到达。公开仓库连续 60 天没有活动时，GitHub 会自动停用定时工作流；届时需在 Actions 中重新启用。需要严格准时、永久无人维护时应改用持续运行的服务或云定时任务。

参考：[GitHub 定时运行规则](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)、[Actions Secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets)、[飞书发送消息接口](https://open.feishu.cn/document/server-docs/im-v1/message/create)。

## 开发验证

```bash
pip install -r requirements-cloud.txt
python -m unittest discover -s tests -v
```

测试使用模拟飞书响应和临时数据库，不会真实发送消息。


## 单次试推美国免费榜

手动运行 workflow 时勾选 `trial_us_free`：榜单范围限定为 App Store 和 Google Play 的美国全部游戏免费榜 Top100，保留已关注公司的监测。若缺少设定窗口的历史，使用窗口内最早的已有快照，并标明实际间隔和短时变化；没有达到阈值时明确说明，同时列出实际上涨项目。完全没有历史时才展示当前前10名快照。公司部分回顾近30天商店首发，明确区分已有近期产品、本轮首次发现与今天新发布。

试推消息标题带“试推”，使用独立投递记录；同一 GitHub 运行重试仅补发失败部分。每天9点的监测范围、公司关注、接收人和当天正式日报记录均保留。此开关默认关闭，定时任务不启用。
