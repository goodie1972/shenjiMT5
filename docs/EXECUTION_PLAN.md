# 神机 MT5 版 — 执行计划（M0~M3）

- 版本：v1.0（2026-10-02）
- 上游：`docs/PRD.md`（目标/非目标/过渡政策）、`docs/contracts/`（三契约）
- 使用方式：每个里程碑开工前勾选任务框；验收标准全绿才算里程碑完成。

---

## 过渡期铁律（全程有效）

1. M2 完成前：**策略改进只进 MT4 版**（唯一准源），MT5 版冻结策略逻辑只动平台代码；MT4 版每次改动记入其 `STRATEGY_CHANGELOG` 备 rebase。
2. M2 完成判据（三者同时满足，不设日期）：FollowAve 四口径报告主口径为正 + MT4 重叠窗口（≥2 个月）信号对齐率 ≥95% + demo 全链路验收通过。
3. MT4 实盘全程照跑，与新库零技术耦合（无共享进程/文件/网络）。
4. M3 实盘稳定 4 周后 MT4 版冻结，再议下线。

---

## M0 — 骨架 + MT5 探路 + 数据入库

**目标**：新库立规矩；MT5 环境一次探明；MT5 数据按新契约入库；数据契约文档从"待回填"变"定稿"。

### 任务

- [x] T0.1 目录骨架 + pyproject + .gitignore + AGENTS.md（Day1 规矩）
- [x] T0.2 三契约文档 v1.0 + 契约测试骨架
- [x] T0.3 `tools/probe_mt5.py` 探测脚本
- [x] T0.4 环境就绪（按 probe 输出的 checklist）：安装 MetaTrader 5 终端 → 开 demo 账户 → `pip install MetaTrader5` → 终端常驻并允许算法交易
      **2026-10-02 实测**：用户已装 MetaTrader 5 build 6231 并登录 **MetaQuotes-Demo**（#113526190，$100k，对冲账户）；MetaTrader5 包 5.0.6231 + Python 3.14.3 兼容。仅剩：**M1 下单前开启终端"算法交易"按钮**（读数据不需要）。现役实盘 = Dukascopy MT4；M3 晋升前建议另开 Dukascopy MT5 demo 做 broker 平价验证（spec 快照按 broker 留档，不覆盖）。
- [x] T0.5 跑 probe：账户模式（净持/对冲）、symbol spec（digits/point/filling/stops）、server offset、M1~D1 rates 可用性、ticks 可用性 → `docs/probe/mt5_probe_report.md`
      **2026-10-02 全部通过**：对冲账户；XAUUSD digits=2/pip=0.01 与旧库惯例一致；server offset +3.00h；全 TF 桶一致率 100%（UTC 域 H4 桶=3600s，同旧库形态）；real ticks 近 6h 9.2 万条（M2 验证层可用）；deals 可读。契约 §4/§8 已回填实测值。
- [ ] T0.5 跑 probe：账户模式（净持/对冲）、symbol spec（digits/point/filling/stops）、server offset、M1~D1 rates 可用性、ticks 可用性 → `docs/probe/mt5_probe_report.md`
- [x] T0.6 `core/mt5_client.py` 转正：offset 校准循环、symbol spec 缓存、下单包装（filling 自适应）通过单测（mock API）——注入式 fake MT5 模块 + `select_filling` 纯函数 + `order_send`（retcode/fail-closed 校验）
- [x] T0.7 数据入库：`engine/data_factory.py` 拉 M1..W1 → to_utc → upsert `ohlcv`；历史回填（terminal 可给的最大范围）
      **实测坑（已固化）**：`copy_rates_from_pos` 单次 ≥100000 根返回 Invalid params → 上限 99999 + `start_pos` 分页回填（`backfill(max_pages=3)`）。入库量：M1 10 万根（~3.5 个月）/ M5 10 万（~1.4 年）/ M15 10 万（~4 年）/ M30 10 万（~8.5 年）/ **H1 10 万（~17 年，2009 起）**/ H4 34179（2004 起）/ D1 5732 / W1 1164。UTC 域桶偏移复验：全 TF 一致率 100%（H4=3600s、D1=75600s）。想加深深度的 M1：终端 设置→图表→最大柱数 调大后重跑 `tools/ingest_ohlcv.py`。
- [x] T0.8 `tools/export_ohlcv_parquet.py` 产出 L2 研究层 + manifest（sha256 校验、六列契约、dedupe/sort/validate；读回验证通过）
- [x] T0.9 `tools/clean_ohlcv.py` 移植三规则，产出 L3；桶偏移众数探测报告回填契约 §4/§8
      **实测结论**：真实数据 0 ghost / 0 重建 / 0 补洞（clean）；新增"闭合桶"约束——右端未闭合桶不评估不补洞（never fabricate；首跑曾把 forming 桶误报为 1 重建 + 1 补洞，已修）。L3 = `ohlcv_clean` 表 + `data/clean/` parquet，评估逻辑抽 `assess_tf` 纯函数带 7 个单测。
- [x] T0.10 `docs/probe/` 巡检惯例建立（每次 M0/M1 会话先跑 probe）→ 已写入 AGENTS.md §7.4

### 验收（2026-10-02 全部达成 ✅）

1. `pytest tests/` 全绿（59 例，含 test_contract_data 全部 schema/UTC/只读/PK 用例）。
2. probe 报告存在且回答了 PRD 的四个 MT5 地雷（R4 对冲、R5 digits=2、R6 offset +3h、R7 环境就绪）。
3. `ohlcv` 各 TF 行数、起止时间、桶偏移一致率 100%（≥95% 达标）。
4. 数据契约 v1.1 §4/§8 回填实测值，标记"M0 定稿"。

---

## M1 — demo 全链路（门禁全开，零真钱）

**目标**：与旧库等价的实盘链路在 demo 账户上跑通；门禁链第一次被真正验证（D2 反转落地）。

### 任务

- [ ] T1.1 `engine/engine.py` 三轨主循环（tick 驱动、线程池 4、跨 bar 刷新）
- [ ] T1.2 `engine/data_factory.py` 转正：本地指标引擎（白名单 56+11 键，pandas 实现）+ `indicator_snapshots` 落库
- [ ] T1.3 `engine/athlete.py`：3-tick 复核、`_verify_entry`、下单（filling 自适应、SL/TP 兜底 2×ATR/4×ATR）、position ticket 记账
- [ ] T1.4 `engine/risk/gatekeeper.py` 转正：G0~G15 有序评估 + `risk_states` 持久化/恢复 + fail-closed
- [ ] T1.5 journal：`closed_trades.jsonl` append-only + signals 生命周期（pending→opened/voided→closed）
- [ ] T1.6 对账：每 6h + 启动时 `history_deals_get` 按 position_id 聚合比对
- [ ] T1.7 `engine/paper_sim.py`（本地模拟器，仅测试注入用）
- [ ] T1.8 注入测试清单全项落地（contract_risk.md §4：T-G0 ~ T-paper）
- [ ] T1.9 首个冒烟策略（最简白盒策略，如"bar1 收阳且 RSI<30 → BUY"）跑 demo 72h 不间断
- [ ] T1.10 运维件：日志轮转、异常重启（脚本）、市场闭市静默

### 验收

1. 注入测试 14 项全绿，特别是 **T-paper：demo 模式下门禁全部同样生效**。
2. demo 账户真实下单/平仓/部分平仓流转正常，journal 与 `history_deals_get` 对账零差异（连续 72h）。
3. 重启恢复：risk_states / 在途信号恢复正确。
4. `pytest` 全绿；72h 冒烟无未处理异常。

---

## M2 — FollowAve 移植 + 回测基线重建

**目标**：旗舰策略（m15/m30_followave）移植并在 MT5 数据上重建基线；达到判据即宣告"M2 完成"，切换准源。

### 任务

- [ ] T2.1 FollowAve 逻辑移植（M15/M30 双周期同向方法论：参数改动需两周期同向为正才采纳）
- [ ] T2.2 指标对齐验证：与旧库重叠期逐 bar 对比 indicator_snapshots（键值容差 ±1e-6，差异须归因 feed）
- [ ] T2.3 回测脚本 `backtest/followave_backtest.py`：逐行复制线上行为口径（**含死参数实况**——旧库 goodma 教训）
- [ ] T2.4 口径锁定：M5 精度挂死、SL 优先歧义保守、入场=信号 bar 下一开盘、ex-riding=剔除数据末端 4h 骑单
- [ ] T2.5 四口径报告：M30/M15 × 全样本/可复现窗口，主口径（ex-riding 后净利差）为正 → PASS
- [ ] T2.6 MT4 重叠窗口对账（≥2 个月）：信号方向一致率 ≥95%
- [ ] T2.7 （加分）real-tick 验证层：`copy_ticks_range` 抽样窗口重放，对比 bar 口径结论不翻转
- [ ] T2.8 策略文档（中/英）+ changelog；rebase 清单（MT4 版 M2 期间的策略改动逐条移植）

### 验收

1. 四口径报告 PASS + 对账达标 → **宣告 M2 完成，策略准源切换为 MT5 版**。
2. `tests/test_contract_strategy.py` 全绿（白名单强制、bar1 静态卡口对 FollowAve 通过）。
3. demo 上 FollowAve 信号与回测信号抽查一致（≥95%）。

---

## M3 — 逐策略验证与晋升

**目标**：其余策略按需逐个走"移植 → demo → 实盘小仓"晋升管道，每策略一份晋升清单。

### 任务（每策略重复）

- [ ] T3.x.1 移植 + 契约测试通过 + 四口径 PASS
- [ ] T3.x.2 demo 跑 ≥2 周无异常，实盘/纸面行为一致性抽查
- [ ] T3.x.3 晋升清单（晋升 = checklist 文件放 `docs/promotions/`）：四口径 PASS、门禁注入回归、对账无差异、小仓手数（0.01）、运行 1 周 SL/TP 实际触发符合预期
- [ ] T3.x.4 实盘小仓上线，观察 2 周写复盘

### 验收（全局）

1. 至少 FollowAve（M15/M30）完成晋升上实盘小仓。
2. 实盘稳定运行 4 周：无门禁漏放行、无对账差异、无 fail-open。
3. 达成后启动 MT4 版冻结评估（PRD §5.4）。

---

## 风险应对速查

| 风险 | 触发信号 | 应对 |
|------|----------|------|
| R1 重复踩坑 | 契约测试失败 / 静态卡口报警 | 修实现不改契约；若契约错则走三处同步流程 |
| R2 范围蔓延 | 任务清单外的工作冒头 | 回 PRD §2.2 非目标清单对照；新增能力先进 PRD 评审 |
| R3 双份维护拉长 | M2 判据 2 个月未达标 | 升级评审：是 feed 差异还是移植缺陷；必要时缩对账窗口重议阈值 |
| R4 账户模式 | probe 发现 netting 账户 | v1 维持并发=1（两模式等价）；写 netting 语义附录后才放开 |
| R5 symbol spec | digits=3 / stops_level 异常大 | 下单包装层已有自适应；契约 §8 回填并在 journal 记录 spec 快照 |
| R6 server time | offset 漂移 >30min 告警 | 校准循环自动更新；probe 巡检复核桶偏移 |
| R7 环境约束 | MetaTrader5 包初始化失败 | probe checklist（64 位 Python、终端路径、允许算法交易、账户登录） |

---

## 当前进度

- 2026-10-02：PRD/架构/三契约/执行计划 v1.0 定稿；骨架 + 契约测试（37 例全绿）+ probe 脚本提交。
- 2026-10-02：**T0.4/T0.5 完成**——MT5 build 6231 + MetaQuotes-Demo 登录，probe 全项通过（对冲账户、digits=2、offset +3h、桶一致率 100%、real ticks 可用）；契约 §4/§8 回填实测值。
- 2026-10-02：**M0 全部任务完成（T0.1~T0.10），验收四项全过，测试 59 例全绿**。数据：L1 8 个 TF 入库（H1 深 17 年）、L2 研究层 parquet + manifest、L3 清洗产物（0 异常）。**下一步：进入 M1（T1.1 三轨主循环起步）**；M1 下单前需开启终端"算法交易"按钮。
