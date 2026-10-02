# m15/m30_followave v1.0 (MT5 版) — 策略文档（中文）

- 移植日期：2026-10-02 ｜ 血统：旧库 `20260927_m{15,30}_followave_v2.py` **v1.6**（逐行移植，逻辑/参数零改动）
- 共享实现：`strategies/followave_core.py`（6 条接口适配点见头注）；薄壳仅差 `TRAIL_ATR`（M30=3.0 / M15=4.0）与 magic（661402 / 661401）

## 入场（全部基于已闭合 bar1）

| 条件 | 多头 | 空头 |
|------|------|------|
| ±DI 门禁 | \|+DI − −DI\| > 2 | 同 |
| 方向 | +DI > −DI | −DI > +DI |
| 位置 | close > BBI | close < BBI |
| Stoch(5,3,3) | 金叉（K>D 且 K_prev≤D_prev） | 死叉（K<D 且 K_prev≥D_prev） |
| 极值过滤 | K < 80 | K > 20 |
| 中轨 | close ≥ BB 中轨 | close ≤ BB 中轨 |

tick 级复核（G15）：价格须在 BBI/中轨正确一侧，forming bar 实体不逆方向。

## 出场（优先级从高到低，全部基于已闭合 K 线）

1. **分批止盈**（引擎钩子）：bar1 收盘达 入场价 ± 3.0×ATR（**入场时冻结**）→ 平 50%，每笔一次
2. **超买/超卖死叉止盈**：曾触 BB 上轨（容差 3 点）+ K>80 死叉（空头镜像 K<20 金叉）
3. **趋势反转**：close 破 BBI 且 bb_mid_direction（SMA20 斜率 ±0.02%）同向，**连续 3 根**
4. **BB 硬止损**：收盘越过对面轨
5. **Trailing Stop**：TRAIL_ATR × ATR 从闭合 K 线极值回撤

SL 兜底：max(3×ATR, 30)，无 TP（出场全托管）。出场归因写 `_last_exit_detail`。

## 参数与历史依据（继承旧库 changelog，禁改）

80/20（v1.3 撤销 70/30）、bb_mid_direction 而非真实 BBI 方向（v1.3 A/B：M15 差 +462.8）、
DI_GATE=2（v1.4）、分批 3.0×ATR 平 50%（v1.5）、TRAIL 3.0/4.0（v1.2）。依据详见旧库文件头注与
`followave_improvement_analysis.md`。**任何改动必须先在 MT4 版发生并验证，再 rebase。**

## MT5 版验证记录

- 移植单测 21 例（`tests/test_followave.py`）：入场/复核/出场优先级/分批/状态冻结/SL
- 四口径回测（MT5 数据，`backtest/reports/followave_four_gate_report.md`）：
  M30 全样本 +2025 / M30 180d +346 / M15 全样本 +2189 / M15 180d +524 —— **PASS**
- 指标对齐（`docs/reports/mt4_overlap_report.md`）：与旧 EA 快照 bias≈0（feed 聚合噪声量级）
- 信号对账：受旧库 signals 表仅存 7 天限制，M15 窗口内 10/15（66.7%，±2bar）；M30 无真值。
  完整验收改由 **M3 前瞻影子运行**承担（demo 与 MT4 实盘同窗对照）
