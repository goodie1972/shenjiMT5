# 契约目录（docs/contracts）— 两仓库的唯一共享物

- 版本：v1.0（2026-10-02）

## 索引

| 契约 | 文件 | 锁定什么 | 对应测试 |
|------|------|----------|----------|
| 策略接口 | `contract_strategy.md` | 六元组信号、bar1 不变量、指标键白名单、退出钩子签名、策略文件纪律 | `tests/test_contract_strategy.py` |
| 数据规范 | `contract_data.md` | ohlcv schema、UTC 时间戳、桶对齐、研究层 parquet、清洗三规则、symbol spec | `tests/test_contract_data.py` |
| 风控门禁 | `contract_risk.md` | G0~G15 有序门禁表、参数锁定表、状态机纪律、注入测试清单 | `tests/test_contract_risk.py` |

## 共享规则

1. **只共享语义，不共享代码。** 旧库（`xauusd`）与本仓库各自独立演进；任何一边 import 另一边模块 = 违约。旧库路径只作只读参考。
2. **契约变更 = 三处同步**：本目录文档 + 双方契约测试 + 双方实现，版本号 +1，写变更记录。单边改动即契约漂移，以先提交的一边为准通知另一方跟进。
3. **契约测试是锁**：`tests/test_contract_*.py` 中参数锁定测试（如 `test_risk_params_locked`）失败 = 违约，CI/本地均不可合入。
4. **方向**：风控参数与 bar1 纪律以旧库实盘验证值为基准源；MT5 语义（UTC、symbol spec、账户模式）以本仓库为准源。旧库不需要反向跟进 MT5 特有节。

## 旧库对应物（只读参考映射）

| 本契约 | 旧库出处 |
|--------|----------|
| contract_strategy | `strategies/base.py`（v2）、`strategies/strategy_manual.md`、`organized_docs/05_规范/CODE_REVIEW_STANDARD.md`、`organized_docs/07_审计报告/STRATEGY_FORMING_BAR_AUDIT.md` |
| contract_data | `data/database.py`、`AGENTS.md` §2/§3/§5、`tools/clean_h1_from_m5.py`、`organized_docs/04_数据回测/data_layer_parquet.md` |
| contract_risk | `config/settings.py`、`engine_standalone/risk_mgr.py`、`engine_standalone/main.py`（各 gate 函数）、`tests/unit/test_risk_mgr.py` |
