# UI / App 设计方案 — 快速出活的路线图

- 版本：v1.0（2026-10-03）
- 决策输入：告警通道取消（用户裁定：只"知晓"不能"处理"徒增麻烦，未来由 App 承载）；UI 必做；App 必做（远期）

## 0. 核心设计原则（从旧库教训出发）

1. **旧库 dashboard（FastAPI+Vue3+构建链）是最大维护面之一**——新库 UI 的第一目标是"零构建链、最小依赖、只读"。
2. **v1 监控面板纯只读**：不提供任何下单/改单/平仓按钮。交易操作永远在引擎/终端完成——UI 是"看"，不是"动"。写操作 = 新的攻击面和 bug 面。
3. **数据层已经齐了**：SQLite（signals/trades/risk_states）+ journal jsonl + 心跳。UI 是纯展示层，不新建任何表。

## 1. 技术选型（为什么这样最快）

| 层 | 选择 | 理由 |
|----|------|------|
| 后端 | **FastAPI + sqlite 只读连接**（~200 行） | 已有技术栈；uvicorn 单进程；只读打开符合数据纪律 |
| 前端 | **HTMX + 服务端模板（Jinja2）**，无 npm、无构建链 | 监控面板 = 读多写少 + 局部自动刷新（hx-trigger="every 5s"），HTMX 正好为此而生；一个 Python 进程搞定 |
| 移动端 | **PWA**（manifest + 响应式 + 手机浏览器加桌面图标） | 同一套代码零额外成本；无需推送（告警已取消）；未来要"真 App"用 TWA 套壳，一行配置 |
| 认证 | 单 token（环境变量配置）+ 仅监听 LAN/127.0.0.1 | 交易系统 API 不裸奔公网；远程访问用 VPN/内网穿透时再加 |
| 部署 | `python tools/run_dashboard.py` 一个进程，端口 8800 | 与引擎解耦（只读 DB），引擎重启不影响面板 |

**明确不做**：React/Vue 构建链、WebSocket 实时推送（轮询够用）、原生 App（PWA 够用再说）、任何写操作。

## 2. 页面清单（三页够用）

### P1 总览（默认页，5s 自动刷新）
- 引擎存活（心跳年龄 + 状态灯）
- 账户：余额/净值/浮盈、当日盈亏、当周盈亏（G3b 熔断状态）
- 持仓列表：策略/方向/手数/开仓价/浮动盈亏/持仓时长
- 风控面板：G0~G15 当前状态一览（绿=放行/红=拦截中/灰=未触发）

### P2 信号与成交流水
- signals 表倒序（方向/状态/门禁拦截原因/时间）——**门禁拦截统计**（近 24h 各 gate 拦截计数）
- trades 表倒序（盈亏、exit_reason、pnl_source=broker/local_est 标注）
- journal 原始记录查看

### P3 影子对照（M3 专用）
- 周报数据可视化：MT5 vs MT4 笔数/方向一致率/盈亏对比（数据源 = weekly_shadow_report 产物）
- 晋升跟踪档链接

## 3. API 草案（全部只读 GET）

```
GET /api/overview     → 账户+持仓+风控状态+心跳
GET /api/signals?limit=100&magic=
GET /api/trades?limit=100&magic=
GET /api/gates        → 最近 24h 门禁拦截统计（从日志/signals 解析）
GET /api/shadow/weekly → 读最新 shadow_weekly_*.md
```

## 4. 分期与工作量

| 期 | 内容 | 工作量 | 时点 |
|----|------|--------|------|
| U1 | 后端只读 API + P1 总览页 | ~1 天 | **✅ 2026-10-03 完成** |
| U2 | P2 流水页 + P3 影子对照页 | ~1 天 | **✅ 2026-10-03 完成** |
| U3 | PWA manifest + 手机适配 + token | ~0.5 天 | **✅ 2026-10-03 完成**（manifest/响应式/可选 token；图标占位未做——安装提示可能不出，浏览器访问不受影响） |
| App | TWA 套壳（PWA 直接打包 APK）或 Flutter | 视需求 | PWA 用着不够再说（大概率不需要） |

**实现现状**：`dashboard/`（queries.py 只读数据层 + app.py 路由）+ `tools/run_dashboard.py`；
端口 8800（`--host 0.0.0.0` LAN 可见）；htmx 本地化（无外链依赖）；测试 7 例。
已脱离会话运行。

**验收测试（Playwright 真浏览器模拟，`tools/qa_dashboard.py`）**：29/29 通过——
三页面渲染断言、指标条 6 格、风控 chips 18 行、ECharts 图表 canvas（K线/权益/
逐笔/每日/门禁饼图/影子对照 6 图）、周期按钮交互、HTMX 5s 刷新、移动端无溢出；
截图留档 `tmp/qa_*.png` 人工复核。改面板代码后重跑即可回归。
曾抓出并修复：drawEq 花括号缺失（JS 语法错误炸掉全部图表）、jget 时序
（base 工具函数提前至 head）、Jinja 过滤器缺失（cls/sign）。

## 5. App 路线（远期）

1. **PWA（U3）就是"手机上的 App"**——加桌面图标、全屏运行，覆盖 90% 的"手机看一眼"需求。
2. 若未来确需原生（比如要推送、要后台刷新）：PWA → TWA（Bubblewrap 一条命令打包，无需重写）→ 只有在 TWA 明确不够时才考虑 Flutter/uni-app。
3. 告警职能（用户已取消推送）：App 内做成"打开即见的健康页"（心跳+风控状态置顶），而不是推送打扰。

## 6. 纪律

- dashboard 代码只读 DB（readonly_connect），违反 = 违约（AGENTS §3）。
- dashboard 进程崩溃不影响引擎（解耦）；引擎崩溃由看门狗负责，不由 dashboard。
- 不做 UI 自动化测试（监控页，坏了重开就好）；契约测试覆盖的仍是引擎层。
