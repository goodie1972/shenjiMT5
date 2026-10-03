# 契约一：策略接口契约（contract_strategy）

- 版本：v1.0（2026-10-02）
- 状态：生效
- 变更流程：改本文件必须同步改 `tests/test_contract_strategy.py` 与 `strategies/base.py`，版本号 +1，并在变更记录写明动机。
- 血统：继承自旧库 `strategies/base.py` v2（六元组、get_indicator、bar1 纪律均经实盘验证），重新表述为 MT5 语义。

---

## 1. 生命周期

```
__init__(magic, timeframe)
    → refresh_data()                      # 取数：注入式数据源，只暴露已闭合序列
    → generate_signal()                   # 打分：纯函数式，只读 self 状态
    → [引擎] GateKeeper G0~G15            # 过滤：策略不自带资力类门禁
    → [引擎] Athlete._verify_entry()      # tick 复核：可选静态钩子
    → [引擎] 下单成交 → mark_extreme_entry(ticket)
    → 持仓期间 [引擎每 tick 调]：
         check_ema20_exit(pos, bid, ask) -> bool
         check_partial_exit(pos, bid, ask) -> float   # 0~1 平仓比例，0=不触发
    → 平仓 → [引擎回调] register_trade_result（风控状态突变）
```

## 2. 信号六元组（S-1，v1.2）

`generate_signal()` 必须返回**六元组或 `None`**：

```python
tuple[Optional[OrderType], int, int, list[str], list[str], dict]   # 正常路径
None                                                               # 无信号（v1.2 合法，等价于六元组 signal=None）
# 可选第 7 项：confidence（float），引擎写入 signals 表
```

- `None` 是旧库策略的自然习惯（FollowAve 等移植代码无信号时返回 None），
  v1.1 及之前"必须六元组"的表述会在 on_tick 层误杀 None 返回——v1.2 修正，
  引擎 `on_tick` 对 None 直接跳过本 tick。
- `signal`：`BUY` / `SELL` / `None`。策略**只表达方向意图**，不指定手数/夹板价（手数由配置，价格由 Athlete 用实时 tick）。
- `factors_*`：人类可读因子字符串列表（进 journal，供复盘归因）。
- `indicator_values`：JSON 可序列化 dict（进 signals 表与 journal 快照）。
- 引擎统一调用 `on_tick()`（负责 refresh_data + 最少 10 根 K 线守卫 + 结果存储 `_last_signal`），**子类不覆写 on_tick**。

## 3. 不变量

### INV-S1 bar1 纪律（repaint 教训，🔴 最高优先级）

1. 一切**确认性指标与状态机判定**只能源自**已闭合 K 线**（序列中 `[-2]`，即 bar1；`[-1]` 是 forming bar）。
2. forming bar（`[-1]`）**仅允许**用于：价格触发、实体方向触发（如 `_verify_entry` 里 `candles[-1].close > candles[-1].open` 这类当刻确认）、展示。
3. 数据层保证：`refresh_data()` 暴露的指标缓存顶层**永远是 bar1 值**；策略拿不到 forming bar 指标。
4. 每根闭合 K 线只处理一次：状态机必须用 `last_processed_bar_time != bar1.time` 守卫。
5. 违反 INV-S1 的代码 = 静态测试卡口（`tests/` 扫描策略文件中的越界访问模式），禁止靠 review 记忆把关。

### INV-S2 指标键白名单

1. 策略禁止自算指标；一切指标经 `get_indicator(name)` / `get_indicator_series(name, n)` 获取。
2. `name` 必须在白名单（§4）内；取未登记键**直接抛错**（旧库教训：kiss/goodma 因动态键不在白名单静默返回 None，23 天零成交）。
3. 白名单是**冻结键表**：新增键 = 契约变更（三处同步 + 版本 +1）；废弃键保留但标记 deprecated。

### INV-S3 时间语义

- 策略内一切时间比较基于 **UTC 秒**（D1）；bar 时间 = 该 bar 开盘时刻（UTC）。
- 禁止 `datetime.fromtimestamp(ts)`（本地时区泄漏）；统一用 `config.settings.utc_dt()`。

## 4. 指标键白名单 v1（冻结自旧库 `_EA_CACHE_KEYS`，56 键）

> 键名是 MT4 版实盘用过的命名资产，原样继承；**数值实现**在 MT5 版全部本地计算（D7），与 EA 无关。

```
rsi, rsi_5, rsi_10, mfi, bb, bb_width,
ema_9, ema_21, ema_34, ema_50, ema_200,
sma_14, sma_20, sma_50,
atr, atr_20, adx, pdi, ndi,
macd, stoch_5_3_3, linear_reg_slope,
volume_sma_20, close, cci, cci_direction, wpr,
demarker, bulls_power, bears_power, force_index,
obv, momentum, std_dev, sar,
ao, osma, ac, bwmfi, ad,
env_upper, env_lower,
rvi_main, rvi_signal,
ichi_tenkan, ichi_kijun, ichi_senkou_a, ichi_senkou_b,
alligator_jaw, alligator_teeth, alligator_lips,
gator_upper, gator_lower,
fractal_upper, fractal_lower
```

补充键（旧库 TA-only 派生键照搬，`bb_mid` 为 MT5 版新增 = BB 中轨 SMA20 单值）：`stoch_rsi`、`stoch_k_prev`、`stoch_d_prev`、`candle_pattern_dir`、`candle_pattern_name`、`bbi`、`bb_mid`、`bb_mid_direction`、`trend`、`price_position`、`mfi_direction`、`rsi_dir_3bar`。

## 5. 退出钩子签名（引擎 ↔ 策略）

| 钩子 | 签名 | 语义 |
|------|------|------|
| `check_ema20_exit` | `(position, bid, ask) -> bool` | 策略自有的完整退出状态机（每 tick 调用）；返回 True = 引擎立即平仓 |
| `check_partial_exit` | `(position, bid, ask) -> float` | 返回 0~1 分批平仓比例；0 = 不触发；同一 position 只允许多阶段各一次 |
| `mark_extreme_entry` | `(ticket)` | 成交回调：冻结入场时点状态（如入场 ATR），供后续退出判定 |
| `get_dynamic_sl_tp` | `(direction, entry_price) -> (sl, tp)` | 出场价；返回 `(None, None)` 时用引擎兜底 2×ATR / 4×ATR |
| `get_adx_data` | `() -> Optional[dict]` | 向引擎暴露 +DI/−DI/ADX 供 G12 使用 |
| `calc_gate_state` | `(direction, price, adx_data) -> dict` | G12 K 线门禁的宿主（位置门禁/追高惩罚/News-Bias），由引擎调用 |
| `_verify_entry` | static `(signal, tick_price, latest_cache) -> bool` | 可选；tick 级入场复核（ forming bar 只准做价格/实体触发，见 INV-S1.2） |

## 6. 策略文件纪律（继承旧库版本管理方法论）

1. 文件名 `{YYYYMMDD}_{name}_v{n}.py`；旧版本移入 `strategies/backup/`，不覆盖不删除。
2. 模块级常量：`STRATEGY_MAGIC`（PP+NN+VV 编码）、`STRATEGY_VERSION`、`STRATEGY_CHANGELOG`（每次逻辑改动必须 +1 条）。
3. 双语文档 `strategies/docs/{name}_cn.md` / `_en.md`：入场/出场/参数/回测口径四节。
4. `scanner.py` 自动发现：目录签名（文件名+mtime）失效重扫；取**首个** `BaseStrategy` 子类；重名告警并跳过。
5. `legacy_magics`：版本升级后的旧 magic 列表，用于自动接管在途旧单。

## 7. MT5 特有语义

1. **position ticket**：MT5 以 position ticket 标识持仓（非订单票）。journal/trades/退出钩子一律用 position ticket；历史对账按 `history_deals_get` 的 position_id 聚合。
2. **并发与账户模式**：v1 单策略并发 = 1（G9），净持/对冲账户在此约束下语义等价。未来放开并发**之前**，必须在本文档新增 §8 定义 netting 语义（同向合并持仓下的加仓/分批平仓/盈亏归属）。
3. **手数与精度**：手数步长、最小手数、价位精度全部来自 symbol spec（D4/D6），策略代码不得硬编码 0.01 或 $0.01/pip。

---

## 变更记录

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-10-02 | 初版：自旧库 base.py v2 + 实盘审计结论重新表述 |
| v1.1 | 2026-10-02 | 白名单补充键新增 `bb_mid`（BB 中轨单值；指标引擎实现时经三处同步登记） |
| v1.2 | 2026-10-03 | S-1 明确 `None` 为合法返回（无信号）——影子运行实测暴露：旧库策略无信号返回 None，v1.1 表述会在 on_tick 误杀（fail-safe 兜住未崩引擎，但策略零信号） |
