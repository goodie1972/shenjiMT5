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

健康巡检（GREEN/YELLOW/RED + 每策略封锁详情与剩余冷却）→ P1 升级；日报/周报生成（10min/午夜）→ 新页面；新闻日历（ForexFactory）→ G1 接线时一起做。

**AI 对话子系统与纸面交易**（v3.1 修订）：这两个不是"被取代物"，而是**自建 AI 底座与纸面模式的架构蓝本**——见 §7.2/§7.5（经 2026-10-04 深度研究修订）。

## 7.2 AI 底座（自建 agent 框架，clean-room 旧库设计）+ PA_Agent 作为技能

### 7.2.1 架构关系（v3.1 修正，用户指正）

> **旧库 agent 子系统 = AI 底座**（工具调用架构，能真正查引擎数据、能对话）；
> **PA_Agent = 底座上的一个分析技能**（它刻意禁用工具调用，`tool_choice:"none"`，
> 设计就是"喂数据→回 JSON"——两阶段分析做成底座上的注册工具 + SKILL.md 提示包，
> 而不是绕过底座的独立页面）。

旧库子系统架构（895 行 ai.py + services/agent/*）已逐行盘点，核心构件与规模：

| 构件 | 旧库实现 | 规模 | 取舍 |
|------|----------|------|------|
| 聊天循环 | SSE 三事件协议（content/tool/done）；工具轮非流式+最终答案 20 字符分块；**最多 5 轮**；`role:tool` 按 tool_call_id 配对；首字节失败整体降级纯流式；400 工具不支持→黑名单 600s 重试一次 | ai.py:593-822 | **照搬不变量**，黑名单机制简化为"重试一次" |
| 工具注册表 | register/call/to_openai_tools（OpenAI JSON-Schema），内置 5 只读工具（positions/indicators/account/trades_history/market_price），包导入时注册，新工具零路由改动 | ~100 行 | **clean-room 重写** + MT5 版工具集 |
| 执行门面 | McpRuntime.execute 模式：名字分发/`to_thread`/超时 30s/异常→字符串/非 str→JSON | ~266 行 | **折叠成 ~40 行**（无 MCP） |
| 会话 | 两张 SQLite 表（chat_sessions/chat_messages）+ ~90 行 CRUD；工具对话只在内存（不落库——v3.1 改进：落库 `context_snapshot` 列） | ai_service.py:57-152 | 照搬 + 工具对话落库 |
| Provider 层 | OpenAI 兼容单路径 + ollama 分支；多 provider CRUD/故障转移/SSRF 门/密钥混淆备份 | llm_provider.py 793 行 | **最小 ~80 行**（活跃 provider + chat/completions），硬化项按需后补 |
| System prompt 组装 | persona（soul.md 双文件）+ 代码级工具纪律块 + 【长期记忆】+ 上下文分节 + 技能摘要 | persona_manager:296-335 | **照搬组装结构** |
| 上下文构建器 | 引擎/持仓/价格/指标/信号/成交/新闻分节 map | context_builder.py | 重写——**旧库 bug 警示**：`_get_engine()` 调用不存在的 `get_instance()` 导致引擎分节全静默死亡，只有 SQLite 分节活着；新库用显式 DI |
| MCP 栈 | 手写 JSON-RPC 客户端 682 行 + runtime/config/marketplace | ~1600 行 | **整体丢弃**（需要时再按旧库设计加回） |
| Skills | SKILL.md = 纯提示包（frontmatter+方法论正文）；聊天只注入摘要不注正文（旧库缺陷） | skill_loader | 照搬概念，**修正：启用技能注入全文** |
| Memory | 每轮后台 LLM 抽取偏好 → 全局滚动 memory.md（≤2000 字符）→ 注入【长期记忆】 | 139 行 | 照搬（自包含、便宜） |

**内置工具集（MT5 版）**：旧库 5 个 + 新增——`get_candles(tf,limit)`、`get_pa_analysis(timeframe)`（→PA sidecar，见 7.2.2）、`get_gate_stats()`、`get_shadow_summary()`。全部只读；**AI 永远不下单**（工具纪律块代码级注入，用户改 soul.md 也删不掉——旧库 v3 设计，照搬）。

**旧库两个反面教材（新库直接修正）**：① 工具经 `sys.modules["dashboard.backend.main"].engine_runner` 摸全局单例（v2 修复过一次，context_builder 又犯）→ 新库**显式依赖注入**；② symbol 硬编码散布 → 统一 settings。

### 7.2.2 PA_Agent 在底座中的位置（AGPL 合规路线不变）

```
面板「AI 参谋」页（SSE 聊天）
   │ 用户提问 → agent 循环（自建底座）
   │   ├─ 工具：get_positions / get_indicators / get_trades_history / ...
   │   └─ 工具：get_pa_analysis(tf) ──HTTP──▶ pa_agent sidecar（独立 venv/进程，AGPL 隔离）
   │                                             │ TwoStageOrchestrator 两阶段分析
   ◀── 流式回答（含 PA 决策 JSON 引用）◀─────────┘ 决策树/置信度
```

- sidecar 独立 venv/进程、不修改 pa_agent 源码（AGPL 合规）；决策 JSON 落 `ai_analysis` 表，与实际走势长期对比
- PA 方法论另做成 `skills/pa_analysis/SKILL.md` 提示包（**修正旧库缺陷：启用技能注入全文**）
- 分析计算（结构/BOS/供需区）做成可测试的纯 Python（无 LLM），由工具返回紧凑 JSON——LLM 只做解读

## 7.5 纸面交易移植（paper_sim，v3.1 新增）

旧库 PaperBridge（802 行，v4）= **装饰器桥**：数据走真 feed、交易本地模拟，策略零感知。深挖出精确语义 + 10 项已知缺陷，移植清单：

**照搬的概念**：BUY@ask/SELL@bid 开、对侧平；PnL = `diff × volume × 100`（合约 100oz/lot，可从 MT5 `SYMBOL_TRADE_CONTRACT_SIZE` 运行时取，修旧库硬编码）；SL/TP tick 轮询判定（BUY 看 bid、SELL 看 ask、touch 即触发、SL 先于 TP、重入保护）；部分平仓=结算比例+保留 ticket+`partial_closed` 标志；trade 行 `mode='paper'` 列（与 demo 同 schema 可比）；双层仓位上限；纸面专属同向浮亏门禁；exit_reason 词表。

**修正的旧债**（旧库 10 项缺陷逐条）：① 手续费 per-lot 可配（旧库每次平仓平收 $0.5、部分平仓账目矛盾）；② partial reason 从调用方透传（旧库硬编码 partial_tp，亏损部分也这么标）；③ 持久化用**单行交易记录**（旧库两行 CSV 三种解析器三种规则——实测踩坑证明脆弱），SQLite `paper_trades` 表；④ SL/TP 判定挂到独立 tick 源并记录**缺口跳空**（旧库休市间隙盲区，纸面结果虚高）；⑤ `ignore_gates` 拆成显式 flags（旧库 `ignore_gates=true` 会泄漏到 live 模式跳过风控块——实锤缺陷）；⑥ 重置语义修正（旧库说"余额归零"实际恢复初始值）。

**本地纸面 vs demo 账户的互补定位**（两者并存）：纸面 = 确定性成交、独立核算（initial_balance+reset）、策略池 mode 隔离、门禁矩阵可选（策略逻辑自由测试）；demo = 真实点差/滑点/执行校准。同一 trade schema，结果可比。

**MT5 特有红利**：保证金从 symbol spec 运行时取（旧库无保证金模拟）；`OnTrade`-式对账可用 `history_deals` 复核。

## 7.3 分期（v3.1，D1~D7）

| 期 | 内容 | 工作量 | 依赖 |
|----|------|--------|------|
| D1 交易中心 | 持仓管理（平仓/改SLTP，确认+重试）、引擎启停按钮、健康巡检条（YELLOW/RED + 每策略封锁详情） | ~1.5 天 | 无 |
| D2 策略中心 | 策略池展示（发现/状态/changelog）+ 每策略 stats 卡（胜率/PF/连亏/盈亏曲线）+ 池编辑（改后重启生效）；热加载后置 | ~1.5 天 | 无 |
| D3 回测中心 | 回测公共框架抽取（数据/口径/ex-riding/报告层）+ 作业 API（submit/status/results/history，**子进程执行**）+ 回测页（四口径 + 成本敏感性 + 权益/明细） | ~2.5 天 | 无 |
| D4 纸面模式 | `engine/paper_sim.py` 装饰器桥（照搬语义+修正 10 债）+ mode 配置（demo/paper 双模式，显式门禁 flags）+ 面板模式切换 + `paper_trades` 表 | ~2 天 | 无 |
| D5 AI 底座 | 自建 agent 框架（聊天循环 SSE/工具注册表/执行门面/会话表/provider 最小层/prompt 组装/persona+memory+skills）+ 内置工具 5+3 + 「AI 参谋」聊天页 | ~2.5 天 | D4（工具查纸面/引擎数据） |
| D6 PA 技能 | pa_agent sidecar（独立 venv，AGPL 隔离）+ `get_pa_analysis` 工具 + `skills/pa_analysis/SKILL.md` + `ai_analysis` 表 | ~2 天（sidecar 调试是主要变数） | D5 + LLM API key |
| D7 日报/周报页 + 新闻日历 | journal 聚合日报；ForexFactory 抓取 + G1 接线 | ~1.5 天 | D1 |
| D8 App 增强 | PWA 图标/安装提示 → TWA 套壳 APK（视需求） | ~1 天 | D1~D3 |

**节奏**：D1~D3 纯面板/工具层先行；D4 纸面模式独立（影子运行不冲突）；D5 底座在 D4 之后（工具能同时查 demo 与纸面数据）；D6 挂 PA。全部完成后旧库 dashboard + AI 子系统被完整替代。

**手动开单的特殊纪律**（若启用）：面板开单 = 绕过策略门禁的"人的决定"，需显式开关 + 二次确认 + journal 标注 `manual`；默认关闭。

## 7.4 明确不做（v3.1 重申）

Vue/构建链、Tauri/PyInstaller 打包、自动更新器、策略上传端点、994 行翻译字典、客户端 TA 重实现、引擎嵌面板进程、AI 下单、MCP 栈（首版；需要外部连接器时按旧库 682 行设计加回）。

## 变更记录

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-10-02 | 初版：PWA 优先路线 |
| v2.0 | 2026-10-03 | U1~U3 交付（FastAPI+HTMX+ECharts 三页面），Playwright 29 断言 |
| v3.0 | 2026-10-03 | 用户裁定 v2 太简单；经旧库 dashboard 与 PA_Agent 深度探索，规划三大中心移植（D1~D3）+ PA_Agent sidecar 集成（D4，AGPL 合规路线）+ 日报/新闻/App 增强（D5~D6） |
| v3.2 | 2026-10-04 | 用户二次裁定：影子对照不为独立导航项——并入「日报周报」页作为 Tab（E 微调层已演示注入卡片）；AI 参谋不新增页面——**升级现有 AI agent**（routes/ai.py + services/agent/*）的工具集（get_pa_analysis/get_gate_stats/get_shadow_summary/get_candles）+ PA 技能包 + soul.md 更新为 MT5 语义，FortuneCat/AiChatPanel 入口保留。D6 内容相应并入 D5；E 微调层 override.js v2 已验证（日报周报页注入 ✓） |
| v3.1 | 2026-10-04 | 用户指正方向：旧库 agent 子系统是 AI 底座（工具调用架构）而非被取代物——v3.1 重写 §7.2（自建 agent 框架 clean-room 蓝本：逐构件规模/取舍/旧库 bug 清单，PA 降为底座上的工具+技能）；新增 §7.5 纸面交易移植（PaperBridge 语义精确盘点 + 10 项缺陷修正清单 + 13 条移植清单）；分期改 D1~D7（纸面模式提前至 D4） |
