# 神机 MT5 — UI/UX 设计系统 v1.0（冻结稿）

- 日期：2026-10-04
- 目的：在 D1~D7 功能实施前**冻结**视觉与交互规范，防止临时变动导致风格漂移。
- 配套样稿：`design/mockups/A.html`（终端密度型）、`B.html`（卡片呼吸型）、`C.html`（侧边栏专业型）——三选一后，未选方向的 tokens 作废，选中方向的本规范即为实现标准。
- 参考基准：TradingView（图表与密度）、Binance（卡片与色彩语义）、GitHub Dark（专业克制）。用户补充的参考网站待提供后校准。

---

## 1. 信息架构（IA）——先定骨架，再定皮肉

### 1.1 导航树（全部页面，冻结）

```
顶栏（常驻）：品牌 ｜ XAUUSD 实时行情（bid/ask/点差）｜ 引擎状态徽章 ｜ 时钟(UTC+8)
导航（按方向不同为顶栏 pills 或左侧栏，条目冻结为 7 项）：
  ├─ 总览        /            行情条+指标条+K线+权益+持仓+风控
  ├─ 交易中心    /trading     持仓管理（平仓/改SLTP）+ 手动开单(默认隐藏) + 引擎启停 + 健康巡检
  ├─ 策略中心    /strategies  策略池卡片 + 每策略 stats + 池编辑 + changelog
  ├─ 回测中心    /backtest    作业提交/进度/结果（四口径+成本敏感性+权益+明细）+ 历史
  ├─ AI 参谋     /ai          聊天（SSE）+ 工具调用过程 + PA 分析触发 + ai_analysis 历史
  ├─ 影子对照    /shadow      MT5vsMT4 图表 + 周报 + 晋升跟踪
  └─ 日报·设置   /reports     日报周报 + 风控参数只读视图 + persona/技能管理（D5/D7）
```

规则：
- N1 导航条目**冻结为 7 项**；新功能必须归入既有页面或作为页内 Tab，不得新增顶级导航。
- N2 任何页面 = 顶栏 + 导航 + 内容区，无弹窗式一级功能。
- N3 移动端（<768px）：导航折叠为底部 Tab 栏（7 项图标化）。

### 1.2 页面 × 功能映射（D1~D7 落位）

| 功能（EXECUTION_PLAN） | 落位页面 | 核心组件 |
|---|---|---|
| D1 持仓平仓/改SLTP | 交易中心 | PositionsTable(可编辑行) + ConfirmDialog |
| D1 引擎启停/健康巡检 | 交易中心 + 顶栏徽章 | EngineControl + HealthBar(GREEN/YELLOW/RED) |
| D2 策略池/stats/changelog | 策略中心 | StrategyCard × N + StatsTile + ChangelogList |
| D3 回测作业/四口径/成本敏感性 | 回测中心 | JobForm + ProgressBar + EquityChart + SensitivityTable + TradesTable |
| D4 纸面模式切换/纸面成交 | 交易中心(模式切换) + 流水(mode 列) | ModeSwitch + PaperBadge |
| D5 AI 聊天/工具调用过程 | AI 参谋 | ChatPanel(SSE) + ToolCallTrace + PersonaEditor |
| D6 PA 分析触发/决策树 | AI 参谋页内 Tab | PATrigger + DecisionTree + AnalysisHistory |
| D7 日报/风控参数视图 | 日报·设置 | ReportList + RiskParamsTable(只读) |
| 影子对照（M3） | 影子对照 | ShadowChart + WeeklyReport |

### 1.3 组件清单（冻结命名，实现与样稿共用词汇）

`StatTile` 指标格｜`ChartPanel`(K线/线/柱，统一容器含周期切换)｜`PositionsTable`｜`GateChip` 风控格｜`GateStrip` 巡检条｜`StrategyCard`｜`StatsTile`(胜率/PF/连亏)｜`JobCard`｜`LogTail`｜`ChatBubble`｜`ToolCallTrace`｜`ConfirmDialog`｜`ModeBadge`(demo/paper/live)｜`HealthBadge`｜`DataTable`(排序/筛选统一行为)｜`SectionCard`(页内 Tab 容器)。

组件行为规则：
- C1 所有表格：数字右对齐 + 等宽字体；盈亏列永远带符号与颜色；空数据显示"暂无"行而非空白。
- C2 所有破坏性操作（平仓/启停/重置）必须过 `ConfirmDialog`，按钮文案含对象名（"平仓 #10796 smoke 0.01"）。
- C3 自动刷新只允许两类：状态类 5s（指标条/持仓/风控），图表类 60s；禁止全页刷新。
- C4 图表容器高度冻结三档：tall 360 / mid 260 / small 220（移动端各 -40）。

---

## 2. 设计 Tokens（三套主题）

> 使用方式：CSS 变量直接采用下表；三套方向共享**语义命名**（--bg/--card/--accent/--up/--down…），只换值。实现时 tokens 写入 `dashboard/static/tokens.css`，组件样式只允许引用变量，禁止硬编码色值。

### 2.1 方案 A「终端密度型」（Terminal）— 参考 Bloomberg/TradingView

| Token | 值 | 用途 |
|---|---|---|
| --bg | #0a0e12 | 页面底 |
| --panel | #10161d | 面板 |
| --panel2 | #151c25 | 面板头部/斑马行 |
| --line | #1d2632 | 边框/分隔 |
| --fg | #c9d4e0 | 正文 |
| --fg-strong | #eef3f8 | 数字/标题 |
| --sub | #7d8b9c | 次要文字 |
| --accent | #f0a63a | 品牌琥珀（品牌/选中/焦点） |
| --accent2 | #35c9e8 | 数据高亮青 |
| --up / --down | #00c8a0 / #ff5c5c | 涨/跌 |
| --warn | #ffb020 | 警告（YELLOW 巡检） |
| --danger | #ff4d4f | 危险操作/RED |

- 字体：正文/标题 `"Segoe UI","Microsoft YaHei",system-ui,sans-serif`；数字/表格 **`"Cascadia Mono",Consolas,monospace`**。
- 字号阶梯：11(辅助)/12(表格/密度文本)/13(正文)/15(小标题)/18(页题)/22(指标数值)。基准 12px，行高 1.45。
- 间距：**4px 基准**（4/8/12/16/20/24），面板内边距 10，面板间距 8，区块 12。
- 圆角：4px（面板 6）；阴影：无（用 1px 边框分层）；密度：高（表格行高 30px）。

### 2.2 方案 B「卡片呼吸型」（Card Air）— 现行 v2 的成熟化

| Token | 值 |
|---|---|
| --bg | #0f1420 |
| --panel | #171e2e |
| --panel2 | #1c2436 |
| --line | #232c40 |
| --fg | #d8dee9 |
| --fg-strong | #f2f5f9 |
| --sub | #8a94a6 |
| --accent | #e8b34b（金） |
| --accent2 | #5b8def（蓝） |
| --up / --down | #26a69a / #ef5350 |
| --warn | #e8b34b |
| --danger | #e05252 |

- 字体：`"Segoe UI","Microsoft YaHei"`；数字 `"Consolas"`。字号阶梯：12/13/14(基准)/16/20/26。行高 1.5。
- 间距：**8px 基准**（8/12/16/20/28），面板内边距 16，面板间距 14。
- 圆角：12（面板）/8（按钮/chips）/20（徽章）；阴影：`0 2px 10px rgba(0,0,0,.25)`；密度：中（表格行高 38px）。

### 2.3 方案 C「侧边栏专业型」（Sidebar Pro）— 参考 GitHub Dark

| Token | 值 |
|---|---|
| --bg | #0d1117 |
| --sidebar | #010409 |
| --panel | #161b22 |
| --panel2 | #1c2129 |
| --line | #30363d |
| --fg | #e6edf3 |
| --fg-strong | #f0f6fc |
| --sub | #8b949e |
| --accent | #58a6ff（蓝） |
| --accent2 | #d2a8ff（紫，AI 相关统一用紫） |
| --up / --down | #3fb950 / #f85149 |
| --warn | #d29922 |
| --danger | #f85149 |

- 字体：`"Segoe UI","Microsoft YaHei"`；数字 `"Cascadia Mono"`。字号阶梯：12/13/14(基准)/16/20/24。行高 1.5。
- 间距：**6px 基准**（6/12/18/24），面板内边距 14，面板间距 12；左侧栏宽 208px（图标态 56px）。
- 圆角：6（面板）/6（按钮）；阴影：无；密度：中高（行高 34px）。

### 2.4 三主题通用语义（任何方向都冻结）

- 涨跌语义：**绿涨红跌**（中国市场习惯可切换红涨绿跌——做成设置项，tokens 换值即可）。
- 状态色：放行/健康 = up 色；拦截/危险 = down 色；警告 = warn；未配置/无数据 = --na #6b7690。
- 对比度：正文对底 ≥ 7:1，次要 ≥ 4.5:1，彩色文字 ≥ 3:1（WCAG AA）。
- 禁止：纯黑 #000、纯白 #fff、彩虹渐变、>2 种品牌色同屏。

---

## 3. 版式与交互规则（冻结）

- L1 栅格：桌面 12 列，内容最大宽 1440（A 为全宽无上限，密度优先）；移动单列。
- L2 页面结构自上而下固定：顶栏 → 页题行（标题+主操作）→ 指标条 → 图表区 → 表格区 → 次要区。
- L3 图表：一律 ECharts，深色主题色板 = `['#e8b34b','#5b8def','#26a69a','#ef5350','#b07de8']`（按方向微调）；K线涨 `--up` 跌 `--down`；持仓入场线 = 虚线。
- L4 刷新：状态类 5s、图表类 60s、聊天流 SSE 推送；所有自动刷新必须有最后一次更新时间显示。
- L5 空态：三态文案（"暂无数据"/"等待开市"/"引擎失联"）+ 对应动作提示。
- L6 加载：图表骨架屏（同尺寸浅色块），表格行闪烁禁用。
- L7 错误：请求失败显示上一次数据 + 顶部细黄条"数据刷新失败 HH:MM"。
- L8 破坏性操作：ConfirmDialog 二段式（显示对象详情 → 输入/点击确认）；live 模式全局红色描边。

---

## 4. 主题 × 组件对照速查

| 组件 | A 终端 | B 卡片 | C 侧栏 |
|---|---|---|---|
| 顶栏 | 28px 命令栏（含符号搜索） | 44px 渐变品牌栏 | 同 B + 左侧 208px 侧栏 |
| 指标条 | 6 格 32px 高，单行 | 6 格 64px，大数字 | 4+2 两行 |
| K线图 | 与右侧盘口/订单同列，可拖分栏 | 双列卡片半宽 | 主区 2/3 宽 |
| 表格 | 行高 30，斑马行 | 行高 38，悬停高亮 | 行高 34，悬停高亮 |
| 门禁 | 文本行内嵌 | chips 网格 | chips 网格 |
| 页切换 | 底部标签页（工作区概念） | 顶部 pills | 左侧栏 |

---

## 5. 验收标准（样稿与实现共用）

1. 三份样稿均可在浏览器打开（自包含，无外链），Playwright 截图人工复核通过。
2. 任一方向选定后：tokens.css 一次成文，组件样式 0 硬编码色值。
3. 全站页面按 §1.1 导航树归位，无第 8 个顶级入口。
4. 对比度抽检（正文/次要/彩色）达 §2.4 标准。
