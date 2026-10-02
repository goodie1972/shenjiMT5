"""tools/realtick_check.py — T2.7 real-tick 抽样验证（加分层）。

对 M30 可复现窗口回测的成交明细（--dump-trades 产物）抽样，用**真实 ticks**
（copy_ticks_range，MetaQuotes demo 终端）验证 bar 口径假设：
1. 成交价是否落在该 bar 的 tick 价区间内（[min bid..max ask] 近似）；
2. bar 开盘价 vs bar 内首个 tick 的偏差（挂"下一开盘成交"口径的隐含滑点）；
3. 结论翻转检查：对每笔抽样交易重估 pnl 与 bar 口径 pnl 的符号一致性。

用法：
  python backtest/followave_backtest.py --dump-trades tmp/followave_m30_trades.csv
  python tools/realtick_check.py tmp/followave_m30_trades.csv
"""

from __future__ import annotations

import csv
import os
import sys
from datetime import datetime, timezone

import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from core.mt5_client import MT5Client  # noqa: E402
from data.parquet_store import load_ohlcv  # noqa: E402

BAR = 1800
SAMPLE_N = 12


def main() -> int:
    trades_path = sys.argv[1] if len(sys.argv) > 1 else "tmp/followave_m30_trades.csv"
    with open(trades_path, encoding="utf-8") as f:
        trades = list(csv.DictReader(f))
    print(f"交易明细 {len(trades)} 笔，抽样 ≤{SAMPLE_N}")

    client = MT5Client()
    client.connect()
    df = load_ohlcv("XAUUSD", "M30")
    times = df["time"].to_numpy(dtype=np.int64)
    opens = df["open"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()

    import random
    import time as _time
    tick_horizon = _time.time() - 3 * 86400     # demo 终端 tick 历史仅保留近期
    recent = [t for t in trades
              if int(times[min(int(t["entry_idx"]), len(times) - 1)]) > tick_horizon]
    if not recent:
        print("⚠️ 最近 3 天无可抽样的成交（等引擎/回测覆盖近期后重试）")
        return 0
    rng = random.Random(42)
    sample = rng.sample(recent, min(SAMPLE_N, len(recent)))

    n_ok, n_flip, slip = 0, 0, []
    for t in sample:
        entry_idx = int(t["entry_idx"])
        bar_ts = int(times[entry_idx])
        ticks = client.copy_ticks("XAUUSD", bar_ts, bar_ts + BAR)
        if not ticks:
            print(f"  ⚠️ ticket {t['ticket']}: 无 tick 数据，跳过")
            continue
        bids = [tk["bid"] for tk in ticks if tk["bid"]]
        asks = [tk["ask"] for tk in ticks if tk["ask"]]
        lo, hi = min(bids), max(asks)
        entry_price = float(t["entry_price"])
        in_range = lo - 0.5 <= entry_price <= hi + 0.5
        first_slip = abs(ticks[0]["ask"] - opens[entry_idx])
        slip.append(first_slip)
        # 符号翻转检查：真实 tick 区间中点重估 pnl 符号
        sign = 1.0 if t["direction"] == "BUY" else -1.0
        mid = (lo + hi) / 2
        est = (float(t["exit_price"]) - mid) * sign
        flip = (est > 0) != (float(t["pnl"]) > 0) and abs(est) > 1.0
        n_flip += 1 if flip else 0
        n_ok += 1 if in_range else 0
        status = "✅" if in_range else "⚠️"
        print(f"  {status} #{t['ticket']} {t['direction']} entry={entry_price:.2f} "
              f"tick区间[{lo:.2f},{hi:.2f}] 开盘滑点≈{first_slip:.2f} "
              f"pnl={t['pnl']} 翻转={'是' if flip else '否'}")
    client.shutdown()

    if not slip:
        print("⚠️ 抽样均无 tick 数据（终端 tick 历史受限），本轮无法验证")
        return 0
    print(f"\n结论：{n_ok}/{len(sample)} 成交价均在 tick 区间内；平均开盘滑点 "
          f"{sum(slip) / len(slip):.2f}；符号翻转 {n_flip}/{len(sample)}（bar 口径结论"
          f"{'不翻转' if n_flip == 0 else '存在翻转，需复核'}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
