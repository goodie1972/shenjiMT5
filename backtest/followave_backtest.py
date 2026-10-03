"""backtest/followave_backtest.py — FollowAve 回测基线重建（T2.3~T2.5）。

口径锁定（T2.4，继承旧库回测方法论）：
1. 基线 = 移植策略代码逐行驱动（本脚本不复制策略逻辑，直接实例化
   FollowAveCore 子类喂数据）——含"死参数实况"（如 SL 兜底 max(3×ATR,30)）。
2. 信号在已闭合 bar j（bar1）判定 → 成交于 bar j+1 开盘（entry_mode=open）。
3. 出场条件在闭合 bar k 评估 → 成交于 bar k+1 开盘；宽止损（动态 SL）在 bar
   内用 high/low 触发、按止损价成交；同 bar 止盈止损歧义保守取 SL 先行。
4. G15 tick 复核不模拟（bar 数据无 tick）——回测为乐观上限，实盘会更严。
5. ex-riding：close_ts 晚于 数据末端-4h 的交易判为骑单，主口径剔除。
6. PnL 口径：0.01 lot = 1 oz，$1 价格变动 = $1（旧库同款），无点差建模。

四口径（T2.5，FollowAve 铁律）：M30/M15 × 全样本/可复现窗口（默认近 180 天），
主口径 = ex-riding 后净利，四口径同向为正 → PASS；任一为负 → FAIL 不入池。

数据源：L2 研究层 parquet（contract_data §5，只读）。
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import deque
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from data.parquet_store import load_ohlcv  # noqa: E402
from engine import indicators as ind  # noqa: E402
from strategies.followave_core import FollowAveCore  # noqa: E402

RIDE_WINDOW_SEC = 4 * 3600
LOT_OZ = 1.0            # 0.01 lot = 1 oz（旧库口径）


@dataclass
class Trade:
    direction: str
    entry_idx: int
    entry_price: float
    ticket: str = ""                 # 出场状态键（= mark_extreme_entry 的键）
    exit_idx: int = -1
    exit_price: float = 0.0
    pnl: float = 0.0                 # 混合值（分批 + 剩余，已扣成本）
    reason: str = ""
    partial_done: bool = False
    fills: list = field(default_factory=list)   # [(idx, price, frac)]


def _series(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """一次性计算全部所需指标序列（bar 对齐，NaN → None）。"""
    close = df["close"]
    bbi = sum(ind._sma(close, n) for n in (3, 6, 12, 24)) / 4.0
    mid, upper, lower = ind._bb_series(df)
    adxf = ind._adx_frame(df)
    stoch = ind._stoch_frame(df)
    atr = ind._wilder(ind._tr(df), 14)
    mid_slope = (mid - mid.shift(1)) / mid.shift(1).replace(0.0, np.nan)
    mid_dir = np.select([mid_slope > 0.0002, mid_slope < -0.0002],
                        ["UP", "DOWN"], default="NEUTRAL")

    def arr(s: pd.Series) -> np.ndarray:
        return s.to_numpy(dtype=float)

    return {
        "bbi": arr(bbi), "pdi": arr(adxf["pdi"]), "ndi": arr(adxf["ndi"]),
        "bb_mid": arr(mid), "bb_upper": arr(upper), "bb_lower": arr(lower),
        "k": arr(stoch["k"]), "d": arr(stoch["d"]),
        "k_prev": arr(stoch["k"].shift(1)), "d_prev": arr(stoch["d"].shift(1)),
        "atr": arr(atr), "mid_dir": mid_dir,
    }


def _ind_at(s: dict, i: int) -> dict:
    def v(key):
        x = s[key][i]
        return None if (isinstance(x, float) and np.isnan(x)) else x

    return {"bbi": v("bbi"), "pdi": v("pdi"), "ndi": v("ndi"),
            "bb": None if v("bb_mid") is None else
            {"upper": v("bb_upper"), "mid": v("bb_mid"), "lower": v("bb_lower")},
            "stoch_5_3_3": None if v("k") is None else {"k": v("k"), "d": v("d")},
            "stoch_k_prev": v("k_prev"), "stoch_d_prev": v("d_prev"),
            "atr": v("atr"), "bb_mid_direction": s["mid_dir"][i]}


def run_backtest(df: pd.DataFrame, strategy_cls, label: str,
                 spread: float = 0.0) -> dict:
    """bar 级事件循环：直接驱动移植策略代码。

    spread：往返成本（$/oz，0.01 lot = 1 oz → 每笔扣 spread $）。
    每笔一次往返（分批出场不增加成本——全部 oz 最终各穿越一次点差）。
    """
    s = df.reset_index(drop=True)
    opens = s["open"].to_numpy()
    highs = s["high"].to_numpy()
    lows = s["low"].to_numpy()
    closes = s["close"].to_numpy()
    times = s["time"].to_numpy()
    n = len(s)
    ser = _series(s)

    strat: FollowAveCore = strategy_cls(magic=0, timeframe=label)
    closed_deque: deque = deque(maxlen=31)

    def feed(i: int):
        """构造策略视图：bar1 = bar i（candles[-2]），forming = bar i+1。"""
        window = list(closed_deque)[-30:]
        forming = s.iloc[min(i + 1, n - 1)]
        strat.candles = window + [C := type(window[-1])(
            time=int(forming["time"]), open=forming["open"], high=forming["high"],
            low=forming["low"], close=forming["close"], volume=forming["volume"])]
        strat._cached_indicators = _ind_at(ser, i)

    trades: list[Trade] = []
    cur: Trade | None = None
    sl_price = 0.0

    def close_trade(t: Trade, exit_idx: int, exit_price: float, reason: str):
        t.exit_idx = exit_idx
        t.exit_price = exit_price
        sign = 1.0 if t.direction == "BUY" else -1.0
        # 混合 PnL：已成交的分批 + 剩余（0.01 lot = 1 oz），扣往返成本
        booked = sum((p - t.entry_price) * sign * LOT_OZ * f for _, p, f in t.fills)
        remain_frac = 1.0 - sum(f for _, _, f in t.fills)
        t.pnl = round(booked + (exit_price - t.entry_price) * sign * LOT_OZ * remain_frac
                      - spread * LOT_OZ, 2)
        t.reason = reason
        trades.append(t)

    for i in range(30, n):
        closed_deque.append(_mk_candle(s, i))
        if cur is not None:
            # 1) 宽止损：bar 内 SL 触发（SL-first 保守）
            hit = (lows[i] <= sl_price) if cur.direction == "BUY" \
                else (highs[i] >= sl_price)
            if hit:
                close_trade(cur, i, sl_price, "sl_triggered")
                cur = None
                continue
            # 2) 出场条件（bar1 = bar i）→ 成交于 bar i+1 开盘
            feed(i)
            view = _view(cur)
            if strat.check_ema20_exit(view, closes[i], closes[i]):
                detail = strat._last_exit_detail or {}
                px = opens[i + 1] if i + 1 < n else closes[i]
                close_trade(cur, i, px, detail.get("exit_type", "strategy_exit"))
                cur = None
                continue
            # 3) 分批止盈（策略内部 partial_done 守卫）
            frac = strat.check_partial_exit(view, closes[i], closes[i])
            if frac > 0:
                px = opens[i + 1] if i + 1 < n else closes[i]
                cur.fills.append((i, px, frac))
                cur.partial_done = True
        else:
            if i + 1 >= n:
                break
            feed(i)
            sig = strat.generate_signal()
            if sig and sig[0] in ("BUY", "SELL"):
                cur = Trade(direction=sig[0], entry_idx=i + 1,
                            entry_price=opens[i + 1], ticket=f"T{i}")
                strat.mark_extreme_entry(cur.ticket)
                sl, _ = strat.get_dynamic_sl_tp(sig[0], cur.entry_price)
                sl_price = sl

    if cur is not None:   # 数据末端仍持仓 → 骑单（主口径剔除）
        close_trade(cur, n - 1, closes[n - 1], "eod_rider")

    last_ts = int(times[-1])
    for t in trades:
        t.reason = t.reason or ("eod_rider" if t.exit_idx >= 0 and
                                times[t.exit_idx] > last_ts - RIDE_WINDOW_SEC else t.reason)
    return summarize(trades, times, label), trades


def _mk_candle(df: pd.DataFrame, i: int):
    from strategies.base import Candle
    r = df.iloc[i]
    return Candle(time=int(r["time"]), open=float(r["open"]), high=float(r["high"]),
                  low=float(r["low"]), close=float(r["close"]), volume=float(r["volume"]))


def _view(t: Trade):
    from types import SimpleNamespace
    return SimpleNamespace(ticket=t.ticket, order_type=t.direction,
                           open_price=t.entry_price, volume=0.01, profit=0.0)


def summarize(trades: list[Trade], times: np.ndarray, label: str) -> dict:
    last_ts = int(times[-1])
    ride_line = last_ts - RIDE_WINDOW_SEC
    riders = [t for t in trades if t.exit_idx >= 0 and times[t.exit_idx] > ride_line]
    kept = [t for t in trades if t not in riders]
    pnls = [t.pnl for t in kept]
    gross_win = sum(p for p in pnls if p > 0)
    gross_loss = -sum(p for p in pnls if p < 0)
    pf = round(gross_win / gross_loss, 2) if gross_loss > 0 else float("inf")
    top5 = sum(sorted(pnls, reverse=True)[:5])
    return {
        "label": label, "n_trades": len(trades), "n_kept": len(kept),
        "n_riders": len(riders), "net": round(sum(pnls), 2),
        "pf": pf, "winrate": round(sum(1 for p in pnls if p > 0) / len(kept) * 100, 1)
        if kept else 0.0, "top5": round(top5, 2),
    }


SPREAD_SWEEP = [0.0, 0.10, 0.20, 0.30, 0.40, 0.50]   # $/oz 往返（0.01 lot 每笔 $）


def main() -> int:
    parser = argparse.ArgumentParser(description="FollowAve 四口径回测")
    parser.add_argument("--repro-days", type=int, default=180)
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--spread", type=float, default=0.0,
                        help="往返成本 $/oz（0.01 lot 每笔扣 spread $）")
    parser.add_argument("--cost-sweep", action="store_true",
                        help="成本敏感性扫描：六档点差 × 四口径")
    parser.add_argument("--dump-trades", default="", help="可复现窗口交易明细 CSV 输出路径")
    parser.add_argument("--out", default=os.path.join(
        REPO_ROOT, "backtest", "reports", "followave_four_gate_report.md"))
    parser.add_argument("--sweep-out", default=os.path.join(
        REPO_ROOT, "backtest", "reports", "followave_cost_sensitivity.md"))
    args = parser.parse_args()

    _last_trades: list = []

    import importlib
    m30_mod = importlib.import_module("strategies.20261002_m30_followave_v1")
    m15_mod = importlib.import_module("strategies.20261002_m15_followave_v1")

    # 四口径配置构建一次，主报告与成本扫描共用
    configs = []
    for tf, mod in (("M30", m30_mod), ("M15", m15_mod)):
        df = load_ohlcv(args.symbol, tf)
        last_ts = int(df["time"].iloc[-1])
        repro_start = last_ts - args.repro_days * 86400
        configs.append((tf, "全样本", df))
        configs.append((tf, f"可复现{args.repro_days}d", df[df["time"] >= repro_start]))

    if args.cost_sweep:
        return _run_cost_sweep(configs, args)

    results, rows = [], []
    all_pass = True
    for tf, window, wdf in configs:
        mod = m30_mod if tf == "M30" else m15_mod
        label = f"{tf}-{window}"
        r, trades = run_backtest(wdf.copy(), _cls_of(mod), label, spread=args.spread)
        if tf == "M30" and window.startswith("可复现"):
            _last_trades.extend(trades)     # 供 real-tick 抽样验证
        results.append(r)
        rows.append(f"| {tf} | {window} | {r['n_trades']} | {r['n_kept']} "
                    f"| {r['n_riders']} | {r['net']} | {r['pf']} | {r['winrate']}% "
                    f"| {r['top5']} |")
        if r["net"] <= 0:
            all_pass = False

    header = ("| 周期 | 窗口 | 总笔数 | 剔骑单后 | 骑单 | 主口径净利 | PF | 胜率 |"
              " Top5 净利 |\n|----|----|------|--------|------|----------|----|----|"
              "------|")
    cost_note = f"含成本 {args.spread}$/oz/笔" if args.spread else "无成本建模"
    verdict = "PASS（四口径同向为正）" if all_pass else "FAIL（存在非正口径，不入池）"
    report = "\n".join([
        "# FollowAve 四口径回测报告（MT5 数据）",
        "",
        f"- 生成：{pd.Timestamp.now(tz='UTC').isoformat()}",
        f"- 数据：L2 研究层 {args.symbol} M15/M30（见 manifest sha256）",
        f"- 口径：信号 bar1 → 下一开盘成交；出场 bar1 评估 → 下一开盘；宽止损 bar 内"
        f" SL-first；ex-riding 4h；PnL $/0.01lot=1oz；{cost_note}；G15 不模拟（乐观上限）",
        f"- 策略：移植自旧库 v1.6，参数零改动（见 strategies/followave_core.py 血统注）",
        "",
        header, *rows, "",
        f"## 结论：**{verdict}**",
        "",
    ])
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(report)
    if args.dump_trades and _last_trades:
        import csv
        os.makedirs(os.path.dirname(args.dump_trades) or ".", exist_ok=True)
        with open(args.dump_trades, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["direction", "ticket", "entry_idx", "entry_price",
                        "exit_idx", "exit_price", "pnl", "reason", "partial"])
            for t in _last_trades:
                w.writerow([t.direction, t.ticket, t.entry_idx, t.entry_price,
                            t.exit_idx, t.exit_price, t.pnl, t.reason,
                            t.partial_done])
        print(f"交易明细 → {args.dump_trades}")
    print("\n".join(rows))
    print(f"\n{verdict}")
    print(f"报告 → {args.out}")
    return 0 if all_pass else 1


def _run_cost_sweep(configs, args) -> int:
    """成本敏感性：六档点差 × 四口径。主口径 = ex-riding 后净利（已扣成本）。"""
    import importlib
    lines = [
        "# FollowAve 成本敏感性报告",
        "",
        f"- 生成：{pd.Timestamp.now(tz='UTC').isoformat()}",
        "- 成本模型：每笔往返扣 spread $（0.01 lot = 1 oz）；分批出场不重复计费",
        "- XAUUSD 现实点差参考：主流经纪商 $0.20~0.40/oz 往返",
        "",
        "| 口径 | " + " | ".join(f"{s:.2f}" for s in SPREAD_SWEEP) + " |",
        "|----|" + "----|" * len(SPREAD_SWEEP),
    ]
    nets_by_config = []
    for tf, window, wdf in configs:
        mod = importlib.import_module(
            "strategies.20261002_m30_followave_v1" if tf == "M30"
            else "strategies.20261002_m15_followave_v1")
        nets = []
        for spread in SPREAD_SWEEP:
            r, _ = run_backtest(wdf.copy(), _cls_of(mod), f"{tf}-{window}", spread=spread)
            nets.append(r["net"])
        nets_by_config.append((tf, window, nets))
        lines.append(f"| {tf} {window} | " + " | ".join(f"{v:g}" for v in nets) + " |")

    # 可承受最大点差 = 六档中最后一个使四口径全正的点差
    survive = None
    for idx, spread in enumerate(SPREAD_SWEEP):
        if all(nets[idx] > 0 for _, _, nets in nets_by_config):
            survive = spread
    lines += ["", "## 结论", ""]
    if survive is None:
        lines.append("- **无任何点差档位四口径全正——策略在成本下不可存活，禁止晋升实盘**")
    else:
        lines += [
            f"- 四口径全正可承受的最大点差 ≈ **${survive:.2f}/oz 往返**（含该档）",
            f"- 晋升门槛：实盘经纪商有效点差（含滑点）需 < ${survive:.2f}；"
            f"超出则本策略在该账户上无利可图",
        ]
    os.makedirs(os.path.dirname(args.sweep_out), exist_ok=True)
    with open(args.sweep_out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"报告 → {args.sweep_out}")
    return 0


def _cls_of(mod):
    """从薄壳模块取策略类。"""
    for attr in vars(mod).values():
        if isinstance(attr, type) and issubclass(attr, FollowAveCore) \
                and attr is not FollowAveCore:
            return attr
    raise RuntimeError(f"{mod.__name__} 无策略类")


if __name__ == "__main__":
    raise SystemExit(main())
