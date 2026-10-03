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
- 面板回归 = `python tools/qa_dashboard.py`（Playwright 29 断言；v1 曾写"不做 UI 自动化测试"，v2 起作废）。

---

# v3 路线图 — 三大中心移植 + PA_Agent 集成（2026-10-03 规划）

> 用户裁定：v2 太简单，"不如直接用 MT5 终端"。要求参照旧库三大中心（交易中心/策略中心/回测中心）扩展，并评估 PA_Agent 集成。经两轮深度探索（旧库 dashboard 49 组件/120 端点全量盘点；PA_Agent 147 模块架构分析），规划如下。

## 7.1 旧库三大中心功能盘点与取舍

### 交易中心（旧库称"交易终端"）

| 旧库功能 | 取舍 | 理由 |
|----------|------|------|
| K线 + 12 指标多窗格（1341 行单体组件 + 300 行客户端 TA 重实现） | **改造复用**：ECharts 实现 K线+EMA/BOLL 叠加+RSI/MACD/ATR 副图，指标服务端算好喂 JSON | 单体组件与客户端 TA 重实现是维护坑 |
| 手动平仓（确认+重试循环）/ 改 SL/TP | **原样复用** | 旧库核实根本没有手动开单——"交易中心"实质是持仓管理；新库面板平仓走自己的 mt5_client，引擎 `_on_position_gone` 兜底同步已就位 |
| 手动开单 | **新增，默认缓** | 面板开单绕过策略门禁（仅 G0/G5 兜底）——做成"显式开启+二次确认" |
| 引擎启停/重启 | **复用** | 面板做进程管理（watchdog/supervisor），不嵌引擎 |
| 引擎嵌在面板进程（EngineRunner） | **坚决丢弃** | GIL 争用 + 耦合，旧库最大架构债 |

### 策略中心

| 旧库功能 | 取舍 | 理由 |
|----------|------|------|
| 策略池卡片（启停/TF/magic 编辑）+ importlib 热加/减 | **复用，分两步**：先只读展示+编辑后重启生效；热加载后置 | 简单可靠优先 |
| 每策略 stats（胜率/PF/连亏/最大连亏，按 magic 族） | **思路原样复用** | trades/signals 齐全，面板 SQL 即算 |
| 上传 .py + AST 危险扫描 | 扫描思路保留，上传不做 | 本地放文件即可；上传=攻击面 |
| markdown 解析逻辑表 + 994 行手翻字典 | **丢弃** | 过度工程 |
| 三重数据源（runtime_config/settings/内存） | **丢弃——单一来源** | 旧库"M-9 越刷越错"bug 链根因 |

### 回测中心

| 旧库功能 | 取舍 | 理由 |
|----------|------|------|
| 作业 API：submit → 数据预检 → status/phases/logs → results/history | **原样复用** | 交互形态成熟 |
| 真实策略逐行回测 | 已有（followave_backtest） | 泛化为参数化作业 |
| 公式 DSL/组合指标→生成策略 | **远期** | 旧库 4 条信号管线并存是清理目标 |
| 回测跑在面板进程线程内 | **改为子进程** | 旧库 GIL 争用/软停止/作业内存丢失三连教训 |

### 三大中心之外值得抄

健康巡检（GREEN/YELLOW/RED + 每策略封锁详情与剩余冷却）→ P1 升级；日报/周报生成（10min/午夜）→ 新页面；新闻日历（ForexFactory）→ G1 接线时一起做。AI 对话子系统（895 行 ai.py：SSE 聊天+工具+MCP+persona）→ 被 PA_Agent sidecar 方案取代。

## 7.2 PA_Agent 集成（AGPL 合规路线）

**它是什么**：PyQt6 桌面应用，AI 辅助 Price Action K线分析。两阶段管线（市场诊断 JSON → 交易决策 JSON：订单建议/入场/SL/TP/置信度/下一根 bar 预测），13 家 LLM 路由（DeepSeek/GLM/Kimi/Qwen/Ollama…），结构化输出校验+重试，经验库（按行情状态检索历史成败案例注入提示词），飞书/PushPlus 通知。**刻意不做工具调用、不碰下单**——"程序算事实 → 提示词 → 校验过的 JSON 回来"，110 个测试文件，工程纪律好，活跃维护。

**关键约束：AGPL-3.0**。核心 Qt-free 可库化（`AppContext` + `TwoStageOrchestrator.submit()` 返回 AnalysisRecord + `FreeChatSession` 多轮追问），但网络交互触发源码义务。**合规路线 = 进程隔离 sidecar**：

```
引擎(K线/journal) ──KlineFrame──▶ pa_agent sidecar（独立 venv/独立进程，
                                     │   自写薄 FastAPI 壳，import 未修改的 pa_agent）
面板「AI 参谋」页 ◀──AnalysisRecord──┘（诊断 + 决策建议 + 置信度 + 决策树）
        人看建议 → 人决定（AI 永远不下单）
```

- 不修改 pa_agent 源码 = 无聚合修改义务；sidecar 代码独立成目录；依赖拖累（PyQt6/akshare 等）隔离在 sidecar venv
- 决策 JSON 落新表 `ai_analysis`：与实际走势对比 = 长期评估 AI 参谋质量
- 追问：FreeChatSession 锚定某次分析多轮对话
- 明确预期：它不给工具调用/MCP（源码主动禁用）——"让 AI 操作引擎"不在其设计内，也不在我们规划内

## 7.3 分期（D1~D6）

| 期 | 内容 | 工作量 | 依赖 |
|----|------|--------|------|
| D1 交易中心 | 持仓管理（平仓/改SLTP，确认+重试）、引擎启停按钮、健康巡检条（YELLOW/RED + 每策略封锁详情） | ~1.5 天 | 无 |
| D2 策略中心 | 策略池展示（发现/状态/changelog）+ 每策略 stats 卡（胜率/PF/连亏/盈亏曲线）+ 池编辑（改后重启生效）；热加载后置 | ~1.5 天 | 无 |
| D3 回测中心 | 回测公共框架抽取（数据/口径/ex-riding/报告层）+ 作业 API（submit/status/results/history，**子进程执行**）+ 回测页（四口径 + 成本敏感性 + 权益/明细） | ~2.5 天 | 无 |
| D4 AI 参谋 | pa_agent sidecar（独立 venv）+ 面板 AI 页 + `ai_analysis` 表 | ~2 天（sidecar 调试是主要变数） | LLM API key |
| D5 日报/周报页 + 新闻日历 | journal 聚合日报；ForexFactory 抓取 + G1 接线 | ~1.5 天 | D1 |
| D6 App 增强 | PWA 图标/安装提示 → TWA 套壳 APK（视需求） | ~1 天 | D1~D3 |

**节奏**：D1、D2 先行（纯面板层）；D3 与影子运行并行；D4 等 LLM key 就位。全部完成后旧库 dashboard 即被完整替代。

**手动开单的特殊纪律**（若启用）：面板开单 = 绕过策略门禁的"人的决定"，需显式开关 + 二次确认 + journal 标注 `manual`；默认关闭。

## 7.4 明确不做（v3 重申）

Vue/构建链、Tauri/PyInstaller 打包、自动更新器、策略上传端点、994 行翻译字典、客户端 TA 重实现、引擎嵌面板进程、AI 下单。

## 变更记录

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-10-02 | 初版：PWA 优先路线 |
| v2.0 | 2026-10-03 | U1~U3 交付（FastAPI+HTMX+ECharts 三页面），Playwright 29 断言 |
| v3.0 | 2026-10-03 | 用户裁定 v2 太简单；经旧库 dashboard 与 PA_Agent 深度探索，规划三大中心移植（D1~D3）+ PA_Agent sidecar 集成（D4，AGPL 合规路线）+ 日报/新闻/App 增强（D5~D6） |
