# AGENTS.md — 神机 MT5 版工程约定

新库 Day1 规矩。本文是给人与 AI 助手的最高优先级工程纪律；契约细节在 `docs/contracts/`，里程碑在 `docs/EXECUTION_PLAN.md`。

## 0. 仓库关系

- 本仓库（`shenjiMT5`）与 MT4 版（`D:\backup\BaoBao\PythonProgram\xauusd`，只读参考）**共享契约、不共享代码**。
- **禁止** import 旧库任何模块；禁止复制旧库文件（例外：`engine/risk/gatekeeper.py` 的状态机纯函数、`strategies/base.py` 的形状，均已重写/重述）。
- 三契约是两库唯一共享物：改动必须三处同步（文档 + 测试 + 实现）并 +1 版本号。

## 1. Day1 规矩（继承教训，不再犯）

1. **git 仓库**：一切工作提交；`tests/` **入库**（旧库把 tests 排除在 git 外是教训）。
2. **根目录净空**：临时文件、补丁、草稿一律进 `tmp/`（已 gitignore）；禁止根目录散落 `.md`/`.patch`/`.log`。
3. **运行时数据不入库**：`data/`（数据库/journal/parquet）、`logs/`、`tmp/`、`config/safety_lock.txt` 均在 `.gitignore`。
4. **临时文件不进提交**：`git status` 出现 `tmp/` 外的意外文件时先清理再提交。
5. **动钱日志**：任何开仓/平仓/改单/门禁拦截必须写日志（策略名、方向、手数、价格、原因、UTC 时间）；平仓必须追加 journal（`data/journal/closed_trades.jsonl`）。
6. **测试随改动走**：改契约实现必须同步改对应 `test_contract_*.py`；修复 bug 必须先有失败测试。

## 2. 时间纪律（契约 contract_data §3 的执行口径）

1. 存储一律 UTC 秒 int64；禁止裸 `datetime.fromtimestamp()` / `datetime.now()`；用 `config.settings.utc_now() / utc_dt() / local_dt()`。
2. 服务器偏移实测不假设：偏移由 `mt5_client` 校准并持久化；漂移 >30min 告警疑似 DST。
3. 桶对齐公式 `((ts − OFFSET) // step) * step + OFFSET`；OFFSET 众数探测，禁止写常量。

## 3. 数据纪律

1. 只读分层：L1 权威库（引擎独占写）→ L2 研究层 parquet（单向导出）→ L3 清洗产物（独立表/文件）。研究代码不写 L1，清洗工具不碰 `ohlcv` 表。
2. 直接用 sqlite3 打开 `market_data.db` 的工具脚本必须 `mode=ro` + `PRAGMA query_only=ON`。
3. `ohlcv_clean` 等 L3 产物必须同时落 parquet 文件留底（旧库 DB 瘦身丢表的事故）。

## 4. 策略纪律

1. bar1 纪律（INV-S1）与指标白名单（INV-S2）见 `docs/contracts/contract_strategy.md`——静态测试卡口强制，不靠 review 记忆。
2. 策略文件：`{YYYYMMDD}_{name}_v{n}.py`；旧版进 `strategies/backup/`；`STRATEGY_CHANGELOG` 每次逻辑改动必须 +1；双语文档四节（入场/出场/参数/回测口径）。
3. 晋升口径：四口径同向为正（M30/M15 × 全样本/可复现窗口）才可入池——回测主口径 = 剔除 ex-riding（数据末端 4h 骑单）后的净利差。

## 5. 风控纪律

1. 门禁唯一执行点：`engine/risk/gatekeeper.py`（G0~G15 有序表，参数锁定见契约 §2）。
2. **fail-closed**：门禁抛错 = 拦截。任何"出错先放行"的写法 = 违约。
3. **无模式旁路**：实盘/demo/模拟器走同一张门禁表；注入测试只存在于 `tests/`。
4. 突变/查询分离：`register_trade_result` 只改状态，`check_*` 纯查询（连亏重复计数的旧回归）。
5. `config/safety_lock.txt` 是物理急停：存在即全局停开新仓；只有人工删除才解锁。任何代码不得自动删除它。

## 6. 版本纪律

- 风控参数改值：先改 `contract_risk.md` §2 → 改 `tests/test_contract_risk.py` → 改 `config/settings.py`。顺序不可反。
- 本文件、三契约、PRD 的变更都要写各自变更记录表。
- 策略 magic 编码沿用 PP+NN+VV（池号+序号+版本），沿用旧库已分配号段避免混淆：6614xx = followave 系。

## 7. 给 AI 助手的操作守则

1. 动手前先读本文件与相关契约；与契约冲突的旧习惯（哪怕来自旧库）一律以契约为准。
2. 不确定旧库某行为的"为什么"时，先查旧库对应文件与 `organized_docs/` 审计报告，再决定照搬或丢弃；照搬要写进契约，丢弃要写进 PRD 丢弃清单。
3. 涉及下单/风控的代码改动，必须运行 `pytest tests/` 全量后再交付。
