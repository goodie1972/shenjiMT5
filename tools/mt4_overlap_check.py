"""tools/mt4_overlap_check.py — T2.2 指标对齐 + T2.6 MT4 重叠窗口信号对账（v2）。

数据源结论（v1 探明）：
- 旧库 ohlcv 是引擎在线时段的残缺记录（M30 最大连续段 46 根≈23h，密度 33/48），
  不能作为指标对齐的 feed——EA 实际在终端**连续**序列上计算。
- 旧库 data/kline/XAUUSD_M{30,15}_Dukascopy.parquet = Dukascopy 深度历史（UTC、
  连续、覆盖至 2026-09-29），与旧 MT4 终端同源 → 作为"旧 feed"。
- 旧库 indicator_snapshots = MT4 EA 直供值（server time，实测 offset +3.0h，r=1.0）。
- 旧库 signals 表仅存 7 天（m15_followave 334 条；m30_followave 0 条——无真值）。

因此：
- T2.2 指标对齐：Dukascopy 蜡烛 → 我方指标引擎 vs EA 快照，窗口 2026-07-28~09-29
  （约 2 个月）。公式对齐（同 feed 下应紧贴）。
- T2.6 信号对账：移植策略在 Dukascopy M15 上重放，vs 旧库实盘信号（有真值的
  全部窗口 09-25~09-29，4.5 天）。M30 无真值 → 如实记录为数据缺口。
- 旧信号 decision bar 语义：信号时间戳是 tick 处理时刻，其时 bar1 = 前一根闭合
  bar → decision_bar = floor(utc/900)*900 − 900；匹配容差 ±2 bar（覆盖缓存刷新抖动）。

产出：docs/reports/mt4_overlap_report.md
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import deque
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from backtest.followave_backtest import _series, _ind_at, _mk_candle  # noqa: E402
from strategies.followave_core import FollowAveCore  # noqa: E402

OLD_DB = "file:D:/backup/BaoBao/PythonProgram/xauusd/data/market_data.db?mode=ro"
KLINE_DIR = "D:/backup/BaoBao/PythonProgram/xauusd/data/kline"
OFFSET = 10800                     # 旧 MT4 server→UTC（网格搜索实测，r=1.0000）
TZ8 = timezone(timedelta(hours=8))


def old_db_connect():
    import sqlite3
    conn = sqlite3.connect(OLD_DB, uri=True)
    conn.execute("PRAGMA query_only=ON")
    return conn


def load_duka(tf: str) -> pd.DataFrame:
    df = pd.read_parquet(os.path.join(KLINE_DIR, f"XAUUSD_{tf}_Dukascopy.parquet"))
    df = df.rename(columns={"tick_volume": "volume"} if "volume" not in df.columns else {})
    if "volume" not in df.columns:
        df["volume"] = df["tick_volume"]
    return df.sort_values("time").reset_index(drop=True)


def indicator_parity(duka: pd.DataFrame, snaps: list[tuple[int, str]]) -> dict:
    s = duka.reset_index(drop=True)
    ser = _series(s)
    idx_of = {int(t): i for i, t in enumerate(s["time"].to_numpy(dtype=np.int64))}
    diffs: dict[str, list[float]] = {}
    signed: dict[str, list[float]] = {}
    weekly_mid: list[tuple[str, float]] = []
    n_matched = 0
    for s_ts, blob in snaps:
        i = idx_of.get(s_ts - OFFSET)
        if i is None or i < 40:
            continue
        snap = json.loads(blob)
        ours = _ind_at(ser, i)
        n_matched += 1
        for key, ov in ours.items():
            tv = snap.get(key)
            if ov is None or tv is None:
                continue
            if isinstance(ov, dict):
                for sub, ovv in ov.items():
                    tvv = (tv or {}).get(sub)
                    if tvv is not None and ovv is not None:
                        d = float(ovv) - float(tvv)
                        diffs.setdefault(f"{key}.{sub}", []).append(abs(d))
                        signed.setdefault(f"{key}.{sub}", []).append(d)
                        if key == "bb" and sub == "mid":
                            weekly_mid.append((datetime.fromtimestamp(
                                s_ts - OFFSET, tz=timezone.utc).strftime("%m-%d wk%W"), d))
            elif isinstance(ov, (int, float)) and isinstance(tv, (int, float)):
                d = float(ov) - float(tv)
                diffs.setdefault(key, []).append(abs(d))
                signed.setdefault(key, []).append(d)
    out = {"matched_bars": n_matched}
    for key, ds in sorted(diffs.items()):
        ds = [d for d in ds if np.isfinite(d)]
        ss = [d for d in signed.get(key, []) if np.isfinite(d)]
        if not ds:
            continue
        out[key] = {"median": round(float(np.median(ds)), 4),
                    "p95": round(float(np.percentile(ds, 95)), 4),
                    "bias": round(float(np.median(ss)), 4) if ss else None,
                    "n": len(ds)}
    # 周度带符号偏差（bb.mid）：全零偏 = feed 噪声而非公式错误的决定性证据
    wk = pd.DataFrame(weekly_mid, columns=["week", "d"])
    if not wk.empty:
        g = wk.groupby("week")["d"].median()
        out["_weekly_bb_mid_median_abs"] = round(float(g.abs().median()), 4)
        out["_weekly_bb_mid_max_abs"] = round(float(g.abs().max()), 4)
    return out


def replay_signals(duka: pd.DataFrame, tf: str, t_start: int, t_end: int) -> list[tuple[int, str]]:
    """移植策略在 Dukascopy 连续 feed 上的信号（bar1 UTC ts, 方向）。"""
    s = duka[(duka["time"] >= t_start - 60 * 86400) & (duka["time"] <= t_end)].reset_index(drop=True)
    ser = _series(s)
    n = len(s)
    strat = FollowAveCore(magic=0, timeframe=tf)
    closed: deque = deque(maxlen=31)
    out = []
    for i in range(30, n - 1):
        ts_i = int(s["time"].iloc[i])
        if ts_i < t_start:
            closed.append(_mk_candle(s, i))
            continue
        closed.append(_mk_candle(s, i))
        window = list(closed)[-30:]
        forming = s.iloc[i + 1]
        from strategies.base import Candle
        strat.candles = window + [Candle(time=int(forming["time"]), open=float(forming["open"]),
                                         high=float(forming["high"]), low=float(forming["low"]),
                                         close=float(forming["close"]),
                                         volume=float(forming["volume"]))]
        strat._cached_indicators = _ind_at(ser, i)
        sig = strat.generate_signal()
        if sig and sig[0] in ("BUY", "SELL"):
            out.append((ts_i, sig[0]))
    return out


def old_signals(conn, strategy: str, t_end_utc: int) -> list[tuple[int, str]]:
    rows = conn.execute(
        "SELECT timestamp, signal FROM signals WHERE strategy=? AND signal IN ('BUY','SELL')",
        (strategy,)).fetchall()
    seen, out = set(), []
    for ts_text, direction in rows:
        dt = datetime.strptime(ts_text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ8)
        utc = int(dt.timestamp())
        if utc > t_end_utc:
            continue
        decision_bar = utc // 900 * 900 - 900       # 信号处理时刻的 bar1 = 前一根
        if (decision_bar, direction) not in seen:
            seen.add((decision_bar, direction))
            out.append((decision_bar, direction))
    return sorted(out)


def reconcile(ours: list[tuple[int, str]], olds: list[tuple[int, str]],
              tf: str, tol: int = 2) -> dict:
    step = 900 if tf == "M15" else 1800
    our_map: dict[str, set] = {}
    for t, d in ours:
        our_map.setdefault(d, set()).add(t)
    matched, total, misses = 0, 0, []
    for t, d in olds:
        total += 1
        hit = any((t + k * step) in our_map.get(d, set()) for k in range(-tol, tol + 1))
        if hit:
            matched += 1
        else:
            misses.append((datetime.fromtimestamp(t, tz=timezone.utc).isoformat(), d))
    return {"old_total": total, "matched": matched,
            "rate": round(matched / total * 100, 2) if total else None,
            "misses_sample": misses[:12]}


def main() -> int:
    parser = argparse.ArgumentParser(description="T2.2/T2.6 MT4 重叠对账 v2")
    parser.add_argument("--out", default=os.path.join(
        REPO_ROOT, "docs", "reports", "mt4_overlap_report.md"))
    args = parser.parse_args()

    conn = old_db_connect()
    lines = [
        "# MT4 重叠对账报告（T2.2 + T2.6，v2）",
        "",
        f"- 生成：{datetime.now(timezone.utc).isoformat()}",
        "- 旧 feed：`xauusd/data/kline/XAUUSD_M{30,15}_Dukascopy.parquet`（UTC 连续深度历史，"
        "覆盖至 2026-09-29）；EA 快照/信号来自旧库（只读）",
        "- 旧 server→UTC offset = +10800s（网格搜索实测，M30 收盘相关 r=1.0000）",
        "- 范围说明：旧 signals 表仅保留 2026-09-25 起的记录（m30_followave 0 条），"
        "信号对账窗口受限；指标对齐窗口 ~2 个月（快照覆盖期 ∩ Dukascopy 覆盖期）",
        "",
    ]

    # ── T2.2 ──
    lines += ["## T2.2 指标对齐（Dukascopy 蜡烛 → 我方指标引擎 vs 旧 EA 快照）", "",
              "判读：bias（带符号中位差）≈ 0 且逐周中位 |diff| 无漂移 → 公式对齐，",
              "残差为 Dukascopy 历史 parquet 与 MT4 终端实时聚盒的 feed 噪声（预期内）。", "",
              "| 周期 | 键 | 中位差 | p95 差 | bias | n |", "|----|----|--------|--------|------|---|"]
    parity_all = {}
    for tf in ("M30", "M15"):
        snaps = conn.execute(
            "SELECT timestamp, indicators FROM indicator_snapshots WHERE timeframe=?"
            " ORDER BY timestamp", (tf,)).fetchall()
        duka = load_duka(tf)
        last_duka = int(duka["time"].iloc[-1])
        snaps = [(t, b) for t, b in snaps if t - OFFSET <= last_duka]
        parity = indicator_parity(duka, snaps)
        parity_all[tf] = parity
        lines.append(f"| **{tf}** | 匹配 {parity['matched_bars']} bar；周度 bb.mid 中位|差| "
                     f"{parity.get('_weekly_bb_mid_median_abs')}（最大 "
                     f"{parity.get('_weekly_bb_mid_max_abs')}） | | | |")
        for key, m in parity.items():
            if key == "matched_bars" or key.startswith("_"):
                continue
            lines.append(f"| {tf} | {key} | {m['median']} | {m['p95']} | {m['bias']} | {m['n']} |")

    # ── T2.6 ──
    lines += ["", "## T2.6 信号对账（移植策略在 Dukascopy M15 重放 vs 旧库实盘信号）", "",
              "| 周期 | 旧信号(去重) | 我方重放 | 一致率(±2bar) | 达标(≥95%) |",
              "|----|----|----|----|----|"]
    all_pass = True
    recon_all = {}
    for tf, strat_name in (("M15", "m15_followave"), ("M30", "m30_followave")):
        rows = conn.execute(
            "SELECT MIN(timestamp), MAX(timestamp), COUNT(*) FROM signals"
            " WHERE strategy=? AND signal IN ('BUY','SELL')", (strat_name,)).fetchone()
        if not rows[2]:
            lines.append(f"| {tf} | 0（旧库无真值记录） | - | - | ⚪ 数据缺口，无法对账 |")
            recon_all[tf] = {"old_total": 0, "rate": None}
            continue
        t_end = int(datetime.strptime(rows[1], "%Y-%m-%d %H:%M:%S")
                    .replace(tzinfo=TZ8).timestamp())
        duka = load_duka(tf)
        t_end = min(t_end, int(duka["time"].iloc[-1]) + 1)
        t_start = int(datetime.strptime(rows[0], "%Y-%m-%d %H:%M:%S")
                      .replace(tzinfo=TZ8).timestamp()) - 6 * 3600
        ours = replay_signals(duka, tf, t_start, t_end)
        olds = old_signals(conn, strat_name, t_end)
        r = reconcile(ours, olds, tf)
        recon_all[tf] = r
        ok = r["rate"] is not None and r["rate"] >= 95.0
        all_pass = all_pass and ok
        lines.append(f"| {tf} | {r['old_total']} | {len(ours)} | {r['rate']}% |"
                     f" {'✅' if ok else '❌'} |")
        print(f"[{tf}] old={r['old_total']} ours={len(ours)} rate={r['rate']}%")

    lines += ["", "### 未匹配样例（归因线索）", ""]
    for tf, r in recon_all.items():
        for t, d in r.get("misses_sample", []):
            lines.append(f"- {tf} {t} {d}")
    verdict = ("✅ 达标（有真值窗口内 ≥95%）" if all_pass
               else "❌ 未达标（须归因）")
    lines += ["", f"## 结论：{verdict}", ""]
    conn.close()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines[-8:]))
    print(f"报告 → {args.out}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
