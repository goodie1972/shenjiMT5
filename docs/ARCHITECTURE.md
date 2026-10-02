# 神机 MT5 版 — 架构设计

- 版本：v1.0（2026-10-02）
- 上游文档：`docs/PRD.md`（决策 D1~D8 在本文落地为模块职责）

---

## 1. 总览

沿用旧库验证过的**三轨架构**（轨道间只经缓存/队列单向流动），但每一轨的底层换成 MT5 原生语义：

```
                     ┌──────────────────────────────────────────────┐
                     │            MT5 终端（Windows 常驻）           │
                     │   XAUUSD 行情 / 下单 / 成交流水(history_deals) │
                     └───────────────┬──────────────────────────────┘
                                     │ MetaTrader5 官方 Python API
                     ┌───────────────┴──────────────┐
                     │  core/mt5_client.py（薄包装） │  ← 唯一终端入口，D4/D5/D6 在此
                     └───────┬──────────────┬───────┘
        （轨道1 数据）        │              │        （轨道3 执行）
               ┌────────────┴───┐   ┌──────┴─────────────────┐
               │  DataFactory   │   │  Athlete（3-tick 复核） │
               │ 拉 rates→bar1  │   │  复核→下单→journal      │
               │ 缓存+SQLite    │   └──────┬─────────────────┘
               └────────┬───────┘          │
        （轨道2 策略）   │                  │
               ┌────────┴──────────────────┴─────┐
               │  策略员：strategies/*.py 扫描池  │
               │  BaseStrategy 六元组信号         │
               └────────┬────────────────────────┘
                        │ 提交 ticket（dict）
               ┌────────┴───────────┐
               │ GateKeeper（G0~G15）│  ← 契约测试锁定（contract_risk.md）
               └────────────────────┘
```

与旧库的差别：**没有 socket EA，没有双桥**。`core/mt5_client.py` 是唯一终端入口；数据与执行共用一个 API 层但各自持独立调用（旧库"双桥"解决的是 MT4 EA 单 socket 排队问题，MT5 API 无此约束）。

## 2. 模块映射（旧 → 新）

| 旧库模块 | 新库对应 | 说明 |
|----------|----------|------|
| `core/freemt4_bridge.py` + `tools/FreeMT4Bridge.mq4`（F 协议） | `core/mt5_client.py` | 全部退役，重写。连接管理、symbol spec、rates/ticks、下单、deals 对账 |
| `core/bridge.py`（create_bridge_pair 双桥） | 无 | MT5 API 无单 socket 瓶颈，双桥语义消亡 |
| `core/paper_bridge.py` | `engine/paper_sim.py`（M1，仅测试用） | 角色反转：旧库为主纸面，新库仅为故障注入测试器；主纸面 = demo 账户（D3） |
| `services/data_factory.py` | `engine/data_factory.py` | 大幅简化：无 F043 双源合并、无 TTL 保护、无 EA 探针。拉 `copy_rates` → 组 bar0/bar1 → 本地算指标 → 缓存 + SQLite |
| `strategies/base.py` | `strategies/base.py` | 形状照搬（六元组、get_indicator、退出钩子），依赖改为注入式数据源；白名单内置强制 |
| `strategies/scanner.py` | `strategies/scanner.py` | 保留自动发现（目录签名 + import + 首个 BaseStrategy 子类） |
| `engine_standalone/main.py`（148KB） | `engine/engine.py` + `engine/core_loop.py` | 拆薄：三轨循环保留，门禁全部外移到 GateKeeper |
| `engine_standalone/risk_mgr.py` | `engine/risk/gatekeeper.py` | **唯一近乎照抄的代码**（纯函数状态机 + StrategyRiskState）+ 门禁表驱动化 |
| `engine_standalone/athlete.py` | `engine/athlete.py` | 保留 3-tick 复核语义（tick_expired → void；`_verify_entry`） |
| `data/database.py` | `data/database.py` | schema 按新契约：timestamp = UTC 秒 |
| F062 对账（`_recover_missing_trades`） | `mt5_client.deals_history()` | MT5 原生全量 deal 流水，按 position ticket 聚合 |
| `dashboard/`（FastAPI+Vue） | 无（v1 非目标） | journal（jsonl + SQLite）够用 |
| `runtime/` 打包 | 无 | 直接跑源码 |
| `tools/clean_h1_from_m5.py`（清洗） | `tools/clean_ohlcv.py` | 三规则照搬（ghost/偏差重建/补洞），桶偏移众数探测照搬 |
| `tools/export_ohlcv_parquet.py` + `data/parquet_store.py` | 同名 | 研究层契约原样（六列 parquet、单向、唯一生产者/读者） |
| `config/settings.py` + `runtime_config.json` | `config/settings.py` + `config/runtime.json` | 保留热重载思想；风控参数值锁定见契约 |

## 3. 目录结构

```
shenjiMT5/
├── AGENTS.md                # 工程约定（Day1 规矩）
├── pyproject.toml
├── config/
│   └── settings.py          # 常量 + 风控参数（数值 = contract_risk.md 锁定值）
├── core/
│   └── mt5_client.py        # MetaTrader5 薄包装（唯一终端入口）
├── data/
│   └── database.py          # SQLite：ohlcv / signals / trades / risk_states
├── engine/
│   ├── data_factory.py      # (M0) rates→bar1 缓存；本地指标
│   ├── engine.py            # (M1) 三轨主循环
│   ├── athlete.py           # (M1) 3-tick 复核 + 下单
│   ├── paper_sim.py         # (M1) 故障注入模拟器（仅测试）
│   └── risk/
│       └── gatekeeper.py    # (M1) 门禁表驱动状态机 G0~G15
├── strategies/
│   ├── base.py              # 策略契约的实现形状
│   ├── scanner.py           # 自动发现
│   └── {YYYYMMDD}_{name}_v{n}.py
├── backtest/                # (M2) 逐策略回测脚本 + 四口径报告
├── tools/
│   ├── probe_mt5.py         # M0 探测：账户模式/symbol spec/时区/数据可用性
│   ├── export_ohlcv_parquet.py  # (M0) 研究层唯一生产者
│   └── clean_ohlcv.py       # (M0) 清洗三规则
├── tests/                   # 契约测试（入库！旧库教训）
│   ├── test_contract_data.py
│   ├── test_contract_risk.py
│   └── test_contract_strategy.py
├── data/                    # 运行时数据（gitignore）
│   ├── market_data.db       # 权威库（唯一写入者：引擎）
│   ├── journal/             # closed_trades.jsonl（append-only）
│   └── am_parquet/          # 研究层（单向只读产物）
├── docs/                    # 本文档体系
└── tmp/                     # 临时文件（gitignore，根目录保持净空）
```

## 4. 数据流

### 4.1 实时循环（每 tick）

```
mt5_client.symbol_info_tick()
  → engine tick：
     ① DataFactory：若跨入新 bar（UTC 对齐桶）→ copy_rates 刷新各 TF
        → merged[-1]=bar0(forming，仅展示/价格触发)  merged[-2]=bar1(闭合，指标唯一来源)
        → 本地指标计算 → 缓存顶层 = bar1 指标 → upsert SQLite
     ② 策略员（线程池并发）：每策略 refresh_data → generate_signal
     ③ GateKeeper.evaluate(context)：G0→G15 有序评估，首个 blocked 即拦截（fail-closed）
     ④ 通过 → signals 表插入 status=pending → Athlete.submit(ticket)
        Athlete：3 tick 内 _verify_entry（bar1 缓存复核）→ 下单（filling 自适应）
        → status=opened(+position ticket)；超时 → voided
     ⑤ Athlete 出场检查：策略退出钩子（check_ema20_exit / check_partial_exit）
        → 平仓 → journal 追加 → trades 更新 → 风控状态突变（register_trade_result）
```

### 4.2 时区模型（决策 D1 落地）

```
MT5 终端返回的 rates/ticks 时间戳 = broker 服务器时间（epoch 秒，含未知偏移）
        │
        ├─ core/mt5_client: server_offset_sec = 服务器最新 tick.time − 本机 UTC
        │   · 启动校准 + 每 6h 重校准；漂移 > 30min → 告警"疑似 DST 切换"（方法论照搬）
        │   · to_utc(ts) = ts − server_offset_sec   ← 入库前统一转 UTC
        │
        └─ 存储：ohlcv.timestamp / trades.* / journal 全部 UTC 秒（int64）
            显示层：UTC+8 格式化（仅展示，禁入库）
桶对齐：bucket = ((ts_utc − day_open_offset) // step) * step + day_open_offset
        day_open_offset 由 probe/工具以众数探测（ts % step 的 mode），不假设 00:00
```

> 注意：与旧库不同，新库**入库即 UTC**，桶偏移探测在 UTC 域进行（旧库在 server-time 域探测出 H4=01:00 UTC 这种常量）。这意味着 H4 桶起点由 broker 日线开市时间决定，每个经纪商不同——所以永远探测、永远不写死。

## 5. 关键技术选型

| 项 | 选择 | 理由 |
|----|------|------|
| Python | 3.10+，**64 位**（MetaTrader5 包硬性要求） | 沿用旧库基线 |
| 终端 API | 官方 `MetaTrader5` 包 | 替代自研 socket EA；同机终端常驻 |
| 指标计算 | 本地计算；后端可换（pandas 实现起步，TA-Lib 可选加速） | 白名单契约只约束**键名**，不约束实现；避免 TA-Lib Windows 二进制依赖阻塞 M0 |
| 存储 | SQLite（WAL）+ pyarrow parquet | 与旧库同型，工具链熟 |
| 测试 | pytest；契约测试三件套 + 门禁注入测试 | 契约双件套机制 |
| 调度 | 单进程线程池（策略并发 4），无外部队列 | 与旧库同规模，不上消息中间件 |

## 6. 风控门禁的架构位置

- **GateKeeper 是唯一的门禁执行点**（旧库分散在 `main.py` 十余处 + `base.py` calc_gate_state，新库收敛为一个模块，策略级 K 线门禁作为 G12 由引擎调用策略的 `calc_gate_state` 呈现）。
- 门禁 = **有序表**（G0→G15），逐条评估，首个 blocked 即拦截，返回 `(gate_id, reason)`；所有放行/拦截写 logs。
- 状态类门禁（连亏/急速/实亏/冷却）的状态机 = `StrategyRiskState` + 纯函数（突变/查询分离），持久化 `risk_states` 表，重启恢复。
- **纸面/演示不旁路**（D2）：`GateKeeper.evaluate(mode=...)` 没有 ignore 分支；故障注入只存在于 `tests/`。
- 详细门禁表：`docs/contracts/contract_risk.md`。

## 7. 对账与 Journal

- `data/journal/closed_trades.jsonl`：append-only，每笔平仓一行（ticket、方向、手数、进出场价、pnl、exit_reason、策略、进出场 UTC 时间、hold_seconds、入场 indicator_values 快照、mode）。
- 定期（每 6h + 启动时）用 `history_deals_get` 拉全量 deals，按 position ticket 聚合，与 `trades` 表比对：缺失补录、exit_reason 以 broker 流水为准可覆盖、数量不符告警。
- signals 生命周期：`pending → opened(+ticket) | voided → closed(+exit_reason)`，与旧库同型。
