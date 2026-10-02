# 神机 MT5 版 — PRD（产品/项目需求文档）

- 版本：v1.0（2026-10-02）
- 状态：已批准（M0 起点）
- 旧库参考（只读，禁止 import）：`D:\backup\BaoBao\PythonProgram\xauusd`
- 本仓库：`D:\backup\BaoBao\PythonProgram\shenjiMT5`（独立演进，不依赖旧库任何模块）

---

## 1. 背景与决策

旧库 `xauusd` 是一套 XAUUSD / MT4 实盘系统：Python 三轨引擎（DataFactory → 策略员 → 运动员）经 socket EA（FreeMT4Bridge，F 协议）驱动 MT4。在旧库上继续打补丁（双桥共存、时区兼容层、历史包袱绕着走）会越改越脏。

**决策：另起干净的 MT5 版本。** 干净的定义是——

> 甩掉 MT4 的**语义和历史**（server time、F043、双桥、runtime 打包、散落文件习惯），
> 甩不掉 MT4 版用**教训换来的契约和方法论**（bar1 纪律、风控门禁、回测口径、研究流程）。

两仓库**共享契约，不共享代码**：各自独立演进，只靠三份契约（`docs/contracts/`）的文档语义 + 双方各自的契约测试对齐。任何一边 import 另一边的模块即为违约。

### 1.1 评审结论（对原迁移建议的五处补强）

原建议（"内核 = 三份契约 + 方法论；M0~M3 四里程碑"）整体成立，以下补强经旧库实码核对：

| # | 补强点 | 实码依据 |
|---|--------|----------|
| 1 | **风控门禁清单比建议多 7 条**：新闻黑屏/新闻偏向、全局日亏 12%、safety_lock 急停（含"疑似快速平仓"自动锁）、账户级浮亏 5%/10%、追高惩罚、全局方向过滤、MTF 共振 | `xauusd/config/settings.py:53-81,283-345`、`engine_standalone/main.py` 各 gate 函数 |
| 2 | **两个口径修正**：①"同向浮亏禁加仓（≤-$0.5）"是纸面专属（实盘靠"单策略并发=1"承担）；②旧库纸面默认 `ignore_gates=True` 绕过门禁 → 新库唯一故意语义反转：**纸面/演示门禁全开** | `main.py:339-343`（ignore_gates 默认 True）、`main.py:2481-2492`（同向浮亏门禁仅纸面分支）、`main.py:2459-2472`（实盘并发=1 单一来源） |
| 3 | **MT5 本地算指标后**，F043 双源/TTL 合并保护整套退役，白名单退化为纯命名契约 | `data_factory.py:199-227`（_EA_CACHE_KEYS + _EA_PROVIDED_TTL 的存在理由随 EA 消失） |
| 4 | **四个 MT5 语义地雷 M0 必须先探明**：净持 vs 对冲账户模式；digits/point 运行时取；filling mode/stops level 自适应；copy_rates 末根仍是 forming bar | 见 §4 语义决策 + `tools/probe_mt5.py` |
| 5 | **M2 完成判据可操作化**：FollowAve 在 MT5 数据上重建四口径基线 + 与 MT4 重叠窗口对账达标，不设日期 | 见 §5 过渡政策 |

---

## 2. 目标 / 非目标

### 2.1 目标

1. **G1**：在 MT5 上重建与旧库等价的实盘能力：数据 → 策略 → 门禁 → 下单 → 对账全链路，零真钱验证后逐策略上实盘。
2. **G2**：三份契约以"规范文档 + pytest 契约测试"双件套固化，复现旧库教训不再靠记忆。
3. **G3**：回测基线在 MT5 数据上重建，沿用旧口径（M5 挂死、SL 优先、ex-riding、四口径同向为正），并有 real ticks 加分验证层（MT5 独有红利）。
4. **G4**：过渡期 MT4 实盘不受任何影响；切换有明确判据而非日期。

### 2.2 非目标（v1 明确不做）

- Dashboard / Web 界面（旧库最大维护面之一；v1 只有 journal：jsonl + SQLite）。
- 多品种（v1 只做 XAUUSD，但 symbol 相关代码不写死 XAUUSD）。
- `runtime/` 式打包发布机制。
- 任何 MT4 桥/EA/F043 的兼容层或继承。
- MT4 时区常量（UTC+3、01:00 UTC 桶）的继承——偏移一律实测。
- 策略全量 23 个一次移植——只按需逐个移植，FollowAve 是参考实现。

---

## 3. 内核定义（迁移什么、丢弃什么）

### 3.1 迁移物（拿形状/规范/规则/方法，基本不拿代码）

| 资产 | 形态 | 迁移方式 |
|------|------|----------|
| **策略形态** | "取数→打分→过滤→出 ticket"模式；六元组信号；bar1 成型 bar 确认纪律（repaint 教训）；指标键白名单 | 拿形状 → `contract_strategy.md`。策略参数按 MT5 feed 重验证，代码重写 |
| **数据规范** | ohlcv schema、只读分层（库→研究层→清洗产物）、清洗管道思想（ghost/偏差/补洞）、桶偏移"实测不假设" | 拿规范 → `contract_data.md`。时区/digits/桶对齐按 MT5 重新定义（**时间戳改 UTC 存储**，这是甩掉牵制的核心） |
| **风控链** | 已验证生效的门禁清单（16 条，见 `contract_risk.md`） | 直接照搬规则与参数——真金白银换来的，与终端无关 |
| **研究方法论** | 回测基线=线上行为逐行复制（含死参数实况）、ex-riding 骑单剔除、四口径晋升（M30/M15 × 全样本/可复现窗口同向为正）、FollowAve 双周期同向、策略版本纪律（dated 文件 + changelog + 双语文档） | 纯方法论，零代码成本，最值钱的资产 → `EXECUTION_PLAN.md` M2/M3 |

少量"干净的代码"允许近乎照抄：`risk_mgr.py` 的纯函数（突变/查询分离的状态机，234 行有测试）与 `StrategyRiskState` 数据类。除此之外不从旧库复制代码。

### 3.2 丢弃清单（坚决不继承）

- MT4 时区假设（server time 存储、UTC+3、H4 桶 = 01:00 UTC 常量）→ 改为 UTC 存储 + 偏移实测。
- F043 协议 / socket EA / 双桥（data+exec 两条 socket）→ MetaTrader5 官方 Python API 一层全替代。
- `runtime/` 打包机制（app 快照 + 内嵌解释器 + reconcile 工具）。
- F062 式对账 → MT5 `history_deals_get` 天然全量流水。
- 根目录散落补丁文件/临时文件的工作习惯 → Day1 规矩（`AGENTS.md`）。
- 纸面 `ignore_gates` 语义 → 反转为门禁全开（§4）。

---

## 4. 关键语义决策（新库第一天定死）

| # | 决策 | 内容 | 与旧库差异 |
|---|------|------|-----------|
| D1 | **时间戳** | `ohlcv.timestamp` 一律存 **UTC Unix 秒**（int64）；显示层 UTC+8；broker 时区偏移**实测不假设**（probe 工具 + 运行时校准，漂移>30min 告警疑似 DST） | 旧库存 MT4 server time（≈UTC+3 且带 ~30min 经纪商时钟怪癖），是最大的历史包袱 |
| D2 | **纸面/演示门禁全开** | 纸面与演示模式**不绕过任何门禁**；唯一允许的旁路是 `tests/` 里的故障注入 | **故意反转**：旧库 `ignore_gates=True` 默认值导致纸面跑不出门禁问题（deliberate deviation） |
| D3 | **纸面 = MT5 demo 账户** | 主"纸面"是 MT5 demo 账户（真实经纪商语义、真实点差/滑点，零风险）；本地模拟器仅用于门禁故障注入测试 | 旧库 PaperBridge 本地模拟为主，验证不了经纪商语义 |
| D4 | **digits/pip 运行时取** | pip 大小、报价精度从 `symbol_info().digits/point` 推导并缓存进 symbol spec；弃用 `$0.01/pip` 硬编码惯例 | 旧库无 digits 常量，隐式约定；不同经纪商 MT5 XAUUSD 有 2/3 位之分 |
| D5 | **账户模式探测** | M0 第一个探测项：`ACCOUNT_MARGIN_MODE` 对冲/净持。v1 门禁按"单策略并发=1"设计，两模式等价；未来放开并发前必须先定 netting 语义 | 旧库无需面对（MT4 天然对冲） |
| D6 | **下单自适应** | filling mode（FOK/IOC/Return）与 stops/freeze level 从 symbol spec 读取，下单包装层按优先级自适应 | 旧库 EA 侧固定行为 |
| D7 | **bar1 纪律保留** | 指标只出已闭合 K 线；forming bar（copy_rates 末根）仅限价格/实体触发。实现简化：本地切片 `[-2]`，不再需要 EA shift=1 / TTL / 双源合并三层防护 | 纪律不变，机制从三层变一层 |
| D8 | **fail-closed** | 门禁评估自身抛错 → 视为 blocked（fail-closed）。旧库曾把 fail-open 标记为缺陷，新库直接纠正 | 旧库 CODE_REVIEW_STANDARD 标记未修 |

---

## 5. 过渡政策

1. **唯一准源**：M2 完成前，策略改进以 **MT4 版为唯一准源**；MT5 版冻结策略逻辑，只动平台代码。
2. **同步机制**：MT4 版每次策略改动记入其 `STRATEGY_CHANGELOG`；M2 完成后一次性 rebase 到 MT5 版（按 changelog 逐条移植），随后跑四口径验证。
3. **M2 完成判据**（三者同时满足，不设日期）：
   - FollowAve（M15/M30）在 MT5 数据上重建回测基线，产出四口径报告，主口径（ex-riding 后净利差）为正；
   - 与 MT4 版在重叠窗口（≥2 个月）逐 bar 信号对账，对齐率达标（指标值一致、信号方向一致率 ≥95%，差异可归因于 feed 差异）；
   - demo 账户全链路（含门禁注入测试）验收通过。
4. **MT4 退役**：M3 实盘稳定运行 4 周后，MT4 版冻结（不再改策略），再议下线。

---

## 6. 里程碑概览（详表见 EXECUTION_PLAN.md）

```
M0  骨架 + MT5 探路 + 数据入库        → 数据规范文档定稿 + 探测报告
M1  demo 全链路（门禁全开，零真钱）    → 注入测试逐条触发 + 对账一致
M2  FollowAve 移植 + 回测基线重建     → 四口径报告 + MT4 重叠期对账达标（切换准源）
M3  逐策略验证与晋升                  → 晋升清单 + 实盘小仓稳定运行
```

---

## 7. 风险登记册

| # | 风险 | 缓解 |
|---|------|------|
| R1 | 重复踩坑（repaint、forming bar、门禁失灵） | 三契约 + 契约测试固化（本 PRD §3.1）；bar1 违规 = 静态测试卡口 |
| R2 | 范围蔓延（全新库容易想重构一切） | §2.2 非目标清单；策略只移植 FollowAve 起步；dashboard 明确不做 |
| R3 | 策略双份维护期拉长 | §5 过渡政策 + M2 完成判据；MT4 准源期间 MT5 不动策略逻辑 |
| R4 | **净持/对冲账户语义**（MT5 特有） | D5：M0 首探；v1 并发=1 使两模式等价；放开前先写 netting 语义附录 |
| R5 | **经纪商 symbol spec 差异**（digits 2/3 位、stops level、filling mode） | D4/D6：运行时取 + probe 报告；下单包装层自适应 |
| R6 | **MT5 仍是 server time**（copy_rates/ticks 按服务器时间戳） | D1：偏移实测 + DST 漂移监控；桶偏移众数探测工具照搬方法论 |
| R7 | MetaTrader5 包环境约束（Windows + 64 位 Python + 终端常驻） | M0 probe 脚本一次性探明并写安装 checklist |
