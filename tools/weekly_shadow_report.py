"""tools/weekly_shadow_report.py — M3 影子运行周报自动化（T3.x.2 周记录）。

对照 MT5（本库 signals/trades，magic 661401/661402）与 MT4（旧库只读）在
窗口期内的信号与成交：方向一致率（±2 bar）、笔数对比、盈亏方向对比。
产出 docs/reports/shadow_weekly_<date>.md，同时打印晋升跟踪档周记录行。

用法：
  python tools/weekly_shadow_report.py            # 最近 7 天
  python tools/weekly_shadow_report.py --days 14
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from config import settings  # noqa: E402
from data import database as db  # noqa: E402
from tools.mt4_overlap_check import old_db_connect  # noqa: E402

MAGICS = {"m15_followave": (661401, "M15"), "m30_followave": (661402, "M30")}
BAR = {"M15": 900, "M30": 1800}
TZ8 = timezone(timedelta(hours=8))


def our_signals(conn, magic: int, t0: int, t1: int) -> list[tuple[int, str]]:
    rows = conn.execute(
        "SELECT created_ts, direction FROM signals WHERE magic=? AND direction IN"
        " ('BUY','SELL') AND created_ts BETWEEN ? AND ?", (magic, t0, t1)).fetchall()
    return [(int(ts) // BAR_step * BAR_step if (BAR_step := BAR_get(magic)) else int(ts), d)
            for ts, d in rows]


def BAR_get(magic: int):
    for _, (m, tf) in MAGICS.items():
        if m == magic:
            return BAR[tf]
    return None


def old_signals(conn, strategy: str, t0: int, t1: int) -> list[tuple[int, str]]:
    rows = conn.execute(
        "SELECT timestamp, signal FROM signals WHERE strategy=? AND signal IN"
        " ('BUY','SELL')", (strategy,)).fetchall()
    out, seen = [], set()
    for ts_text, direction in rows:
        dt = datetime.strptime(ts_text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ8)
        utc = int(dt.timestamp())
        if not (t0 <= utc <= t1):
            continue
        step = BAR["M15"] if "m15" in strategy else BAR["M30"]
        decision_bar = utc // step * step - step    # 信号处理时刻的 bar1 = 前一根
        if (decision_bar, direction) not in seen:
            seen.add((decision_bar, direction))
            out.append((decision_bar, direction))
    return sorted(out)


def agree_rate(ours: list[tuple[int, str]], olds: list[tuple[int, str]],
               step: int, tol: int = 2) -> tuple[float, int, int]:
    our_map: dict[str, set] = {}
    for t, d in ours:
        our_map.setdefault(d, set()).add(t)
    matched = total = 0
    for t, d in olds:
        total += 1
        if any((t + k * step) in our_map.get(d, set()) for k in range(-tol, tol + 1)):
            matched += 1
    return (round(matched / total * 100, 1) if total else None), matched, total


def main() -> int:
    parser = argparse.ArgumentParser(description="影子运行周报")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--out-dir", default=os.path.join(REPO_ROOT, "docs", "reports"))
    args = parser.parse_args()

    t1 = int(settings.utc_now())
    t0 = t1 - args.days * 86400
    ours_conn = db.readonly_connect()
    old_conn = old_db_connect()

    lines = [f"# 影子运行周报（{datetime.fromtimestamp(t0, tz=timezone.utc):%Y-%m-%d} ~ "
             f"{datetime.fromtimestamp(t1, tz=timezone.utc):%Y-%m-%d} UTC）", ""]
    all_rows = []
    for strategy, (magic, tf) in MAGICS.items():
        ours = our_signals(ours_conn, magic, t0, t1)
        olds = old_signals(old_conn, strategy, t0, t1)
        rate, matched, total = agree_rate(ours, olds, BAR[tf])
        # 成交对比
        ours_trades = ours_conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(pnl),0) FROM trades WHERE magic=?"
            " AND close_ts BETWEEN ? AND ?", (magic, t0, t1)).fetchone()
        # 旧库 trades：close_time 是 UTC+8 文本 → Python 解析过滤
        rows = old_conn.execute(
            "SELECT close_time, pnl FROM trades WHERE strategy=?", (strategy,)).fetchall()
        ot_n, ot_pnl = 0, 0.0
        for close_time, pnl in rows:
            try:
                ct = datetime.strptime(close_time, "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ8)
            except ValueError:
                continue
            if t0 <= int(ct.timestamp()) <= t1:
                ot_n += 1
                ot_pnl += float(pnl or 0.0)
        old_trades = (ot_n, round(ot_pnl, 2))
        lines += [
            f"## {strategy}（{tf}）", "",
            f"- 信号：MT5 {len(ours)} / MT4 {total}"
            f"{f'，方向一致率 {rate}%（±2bar）' if rate is not None else ''}",
            f"- 成交：MT5 {ours_trades[0]} 笔 / 盈亏 {ours_trades[1]:.2f} ｜ "
            f"MT4 {old_trades[0]} 笔 / 盈亏 {old_trades[1]:.2f}", "",
        ]
        all_rows.append(f"| {tf} | {len(ours)} | {total} | {rate if rate is not None else '-'} "
                        f"| {ours_trades[0]} | {old_trades[0]} | {ours_trades[1]:.2f} "
                        f"| {old_trades[1]:.2f} |")

    lines += ["## 周记录行（粘贴进晋升跟踪档）", "",
              "| 期间 | MT5 信号 | MT4 信号 | 一致率 | MT5 笔数 | MT4 笔数 | MT5 盈亏 | MT4 盈亏 |",
              "|----|----|----|----|----|----|----|----|", *all_rows, ""]
    ours_conn.close()
    old_conn.close()

    os.makedirs(args.out_dir, exist_ok=True)
    out = os.path.join(args.out_dir,
                       f"shadow_weekly_{datetime.now(timezone.utc):%Y%m%d}.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"报告 → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
