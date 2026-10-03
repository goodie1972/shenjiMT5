# 契约三：风控门禁契约（contract_risk）

- 版本：v1.0（2026-10-02）
- 状态：生效（参数值已逐条核对旧库实码，见"血统"列）
- 变更流程：改本文件必须同步改 `tests/test_contract_risk.py`（**参数值锁定测试**）与 `engine/risk/gatekeeper.py`，版本号 +1。
- 原则：**这张表是真金白银换来的，与终端无关，逐字照搬**；执行机制按新架构收敛到 GateKeeper。

---

## 0. 总则

1. **唯一执行点**：所有门禁收敛于 `engine/risk/gatekeeper.py` 的有序评估表；策略/引擎其他位置不得散落资力检查。
2. **有序评估**：按下表 G0→G15 顺序逐条评估，首个 blocked 即拦截，返回 `(gate_id, reason)`；每次放行/拦截写日志（"动钱"日志纪律见 AGENTS.md）。
3. **fail-closed**（D8）：门禁评估自身抛错 = blocked，reason 注明 `gate_error`。旧库曾标记 fail-open 为缺陷未修，新库直接纠正。
4. **模式无旁路**（D2，对旧库的故意反转）：实盘 / demo / 本地模拟器三种模式**全部走完整门禁表**。旧库纸面默认 `ignore_gates=True` 导致纸面从未验证过门禁链——新库禁止任何 ignore 分支；注入测试只存在于 `tests/`。
5. **状态持久化**：策略风控状态落 `risk_states` 表，重启恢复（旧库 `main.py` 启动恢复逻辑照搬语义）。

## 1. 有序门禁表

参数符号见 §2；`【源】`标注参数出处（旧库文件:行），均为实码核对。

### 账户/环境级（每 tick，全局一次）

| ID | 门禁 | 触发条件 → 动作 | 参数 | 【源】 |
|----|------|----------------|------|--------|
| G0 | **安全急停** | ① `config/safety_lock.txt` 存在 → 全局停开新仓（直至手动删除）；② **疑似快速平仓自动锁**：持仓 < `MIN_HOLD_SECONDS`（30s）且亏损平仓 → 自动落锁 | timeout 永久级 | settings.py:81；main.py `_lock_new_entries` |
| G1 | **新闻黑屏** | 高影响经济数据（默认 High 级、USD）发布前 `NEWS_BEFORE_MINUTES` 至发布后 `NEWS_AFTER_MINUTES` → 停开新仓 | before=30min, after=120min, impact=High, ccy=USD | settings.py:283-289 |
| G1b | 新闻前收紧/强平（可选，v1 配置默认关） | 事件前 120min 收紧止损、前 15min 强制平仓 | tighten=120, close=15 | settings.py:286-287 |
| G2 | **新闻偏向封锁** | News-Bias 预判与开仓方向相悖 → 拦截；ADX ≤ `NEWS_BIAS_ADX_GATE`（震荡市）或 \|+DI−−DI\| < `news_bias_di_gap` 时绕过 | adx_gate=25, di_gap=8；**旧库默认关**（block_long/short=False），新库保持配置默认关 | settings.py:296-301,344 |
| G3 | **全局日亏硬停** | 当日已实现亏损 ≥ `MAX_DAILY_LOSS_PCT`% 余额 → 所有策略停开新仓（5 分钟结果缓存） | 12.0% | settings.py:54 |
| G3b | **周回撤熔断** | 当周（UTC 周一起算）已实现亏损 ≥ `weekly_max_drawdown_pct`% 余额 → 全局停开新仓，**下周一 UTC 00:00 自动解除**（比日亏线更高一级的熔断） | 15.0% | v1.1 新增 |
| G4 | **账户级浮亏** | 单策略浮动亏损 ≥ 5% 余额 → 警告日志；≥ 10% → 禁止该策略开新仓，浮亏回落自动恢复 | warn 5% / block 10% | settings.py:63-64 |
| G5 | **市场开市** | 周末/休市 → 不出候选票不开仓 | — | main.py `_is_market_open` |

### 策略级（每策略每信号）

| ID | 门禁 | 触发条件 → 动作 | 参数 | 【源】 |
|----|------|----------------|------|--------|
| G6a | **实亏百分比封锁** | 单策略累计已实现亏损 ≥ `PER_STRATEGY_REALIZED_LOSS_PCT`% 余额 → 封锁 `PER_STRATEGY_LOSS_BLOCK_HOURS` | 5% → 12h | settings.py:67-68；risk_mgr.check_realized_loss_pct |
| G6b | **实亏绝对额封锁** | 单策略累计已实现亏损 ≤ −`PER_STRATEGY_REALIZED_LOSS_AMOUNT` → 封锁 12h；**PnL 回正自动解除** | $30 → 12h | settings.py:76；risk_mgr.check_realized_loss_amount；main.py:1032-1044 |
| G7 | **连亏封锁** | 连续亏损 `MAX_CONSECUTIVE_LOSSES` 次 → 封锁 `CONSECUTIVE_LOSS_COOLDOWN_HOURS`；**pnl==0 不计数不清零** | 3 次 → 4h | settings.py:77-78；risk_mgr.register_trade_result/check_consecutive_loss |
| G8 | **急速出场封锁** | `RAPID_EXIT_WINDOW_SECONDS` 内出场 ≥ `MAX_RAPID_EXITS` 次 → 封锁 `RAPID_EXIT_COOLDOWN_SECONDS` | 3 次/300s → 7200s(2h) | settings.py:71-73；risk_mgr.check_rapid_exit |
| G9 | **并发上限** | 实盘单策略同时持仓 ≥ `PER_STRATEGY_MAX_POSITIONS` → 拦截；纸面用 `paper_trading.max_positions`；策略池 `max_positions` 仅保留 0=禁用语义 | **实盘 = 1**（单一来源） | settings.py:56-60；main.py:2459-2472 |
| G9b | **账户级并发上限** | 全部策略合计持仓 ≥ `max_total_positions` → 拦截（未来放开单策略并发后的总闸） | 6 | v1.1 新增 |
| G10 | **同向浮亏禁加仓** | 存在同向持仓且其合计浮动 PnL < −`SAME_DIR_FLOAT_LOSS_BLOCK` → 禁止该方向加仓 | $0.5 | main.py:2481-2492 |
| G11 | **盈利平仓同向冷却** | 策略盈利平仓后，`PROFIT_EXIT_COOLDOWN_HOURS` 内不再开**同向**新仓 | 2h | settings.py:348；main.py:2500-2510 |
| G12 | **K 线门禁**（宿主在策略 `calc_gate_state`） | ① 位置门禁：M30 `position_gate_m30_lookback` 根区间，价格处于底部 10% 禁空、顶部 90% 禁多（\|+DI−−DI\| > 20 跳过）；② 追高惩罚：M30 `rally_drop_lookback` 根内从极值偏离 > 1.5% 且 ADX ≤ 25 → 禁追；③ News-Bias 方向块（联动 G2） | lookback=40, 底/顶=0.10/0.90, di_skip=20, rally=30 根/1.5%, adx_skip=25 | settings.py:307-345 |
| G13 | **全局方向过滤** | `GLOBAL_DIRECTION_FILTER` = BUY_ONLY / SELL_ONLY 时拦截反向信号 | 默认 BOTH | main.py:2519-2524 |
| G14 | **MTF 共振门** | H1+M15 TA-Lib 形态共振方向门（`mtf_resonance_enabled`） | 可配置 | settings.py:324 |
| G15 | **Athlete 复核** | 提交后 3 tick 内 `_verify_entry`（bar1 缓存复核）；超时/复核失败 → void（不入场不告警） | 3 tick | 旧库 athlete.py（_MAX_TICKS=3） |

### 评估顺序说明

账户级（G0→G5）每 tick 全局一次；策略级（G6→G14）在策略线程内按序评估；G15 在 Athlete 执行轨。G0 优先级最高（急停压倒一切）；G12 依赖策略数据故置于信号之后仍先于提交。

## 2. 参数锁定表（测试断言依据）

```python
RISK_PARAMS = {
    "max_daily_loss_pct":               12.0,
    "weekly_max_drawdown_pct":          15.0,    # v1.1：周回撤熔断（周一 UTC 自动解除）
    "max_total_positions":              6,       # v1.1：账户级并发总闸
    "per_strategy_max_positions":       1,
    "floating_loss_warn_pct":           5.0,
    "floating_loss_block_pct":          10.0,
    "per_strategy_realized_loss_pct":   5.0,
    "per_strategy_loss_block_hours":    12,
    "per_strategy_realized_loss_amount": 30.0,   # realized_pnl <= -30.0 触发
    "max_consecutive_losses":           3,
    "consecutive_loss_cooldown_hours":  4,
    "max_rapid_exits":                  3,
    "rapid_exit_window_seconds":        300,
    "rapid_exit_cooldown_seconds":      7200,
    "profit_exit_cooldown_hours":       2,
    "min_hold_seconds":                 30,      # 疑似快速平仓自动锁
    "same_dir_float_loss_block":        0.5,     # 纸面同向浮亏禁加仓阈值
    "news_before_minutes":              30,
    "news_after_minutes":               120,
    "news_bias_adx_gate":               25,
    "news_bias_di_gap":                 8,
    "position_gate_m30_lookback":       40,
    "position_gate_bottom":             0.10,
    "position_gate_top":                0.90,
    "di_gate_skip_threshold":           20,
    "rally_drop_lookback":              30,
    "rally_drop_threshold":             1.5,
    "rally_drop_adx_skip":              25,
}
```

`tests/test_contract_risk.py::test_risk_params_locked` 逐键断言以上数值；改值必须先改本契约。

## 3. 状态机（近乎照抄旧库 risk_mgr.py 的纯函数设计）

`StrategyRiskState`（每策略一份）：`realized_pnl / floating_pnl / exit_timestamps(deque) / consecutive_losses / {realized_loss, realized_loss_amount, consecutive_loss, rapid_exit}_blocked{,_at}`。

**突变/查询分离纪律**（旧库双调用重复计数回归的教训）：

- `register_trade_result(state, pnl)`：唯一允许改 `consecutive_losses` 的地方。pnl<0 → +1；pnl>0 → 清零；**pnl==0 不变**。
- `check_consecutive_loss(state, max)` / `check_rapid_exit(state, window, max, now)` / `check_realized_loss_{amount,pct}(...)`：纯查询，不修改任何状态。
- `prune_exit_window(state, window, now)`：每 tick 主动调用，维护窗口。
- `is_*_blocked(state, cooldown, now)`：冷却到期判定。

## 4. 注入测试清单（M1 验收 = 逐条触发）

| 用例 | 注入 | 期望 |
|------|------|------|
| T-G0 | 写 safety_lock.txt | 全局停开仓；删除后恢复 |
| T-G0b | 模拟持仓 20s 亏损平仓 | 自动落锁 |
| T-G3 | 注入日亏 13% | 所有策略停开新仓 |
| T-G3b | 注入周亏 16% | 全局停开新仓；模拟下周一 → 自动解除 |
| T-G4 | 注入浮亏 11% | 该策略禁开仓；回落到 9% 恢复 |
| T-G6a | 单策略实亏 -5.1% 余额 | 封锁 12h |
| T-G6b | 单策略实亏 -$31 → 随后 +$5 | 封锁 → 回正自动解除 |
| T-G7 | register_trade_result(-1)×3 | 封锁 4h；中间插入 0 盈亏不影响计数 |
| T-G8 | 300s 内 3 次出场 | 封锁 2h；窗口外出场不计数 |
| T-G9 | 已持 1 仓再出信号 | 拦截（实盘） |
| T-G9b | 账户合计 6 仓 + 新信号 | 拦截 |
| T-G10 | 同向浮亏 -$0.6 + 新信号 | 拦截加仓 |
| T-G11 | 盈利平仓后 1.9h 同向信号 | 拦截；2.1h 放行 |
| T-G12 | 构造 M30 顶部 95% 区间 BUY | 位置门禁拦截；DI 差 25 时跳过 |
| T-fail | 注入门禁函数抛错 | fail-closed：blocked + gate_error |
| T-paper | demo/模拟器模式跑上述全部 | **门禁全部同样生效**（D2 反转验证） |

---

## 变更记录

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-10-02 | 初版：16 条门禁全量照搬旧库实码参数；新增 fail-closed 与"纸面门禁全开"两项语义决策 |
| v1.1 | 2026-10-03 | 新增 G3b 周回撤熔断（15%，周一 UTC 自动解除）与 G9b 账户级并发总闸（6）——实盘晋升前的仓位规模规则缺口（原契约只锁"能不能开"，没锁"账户总敞口"） |
