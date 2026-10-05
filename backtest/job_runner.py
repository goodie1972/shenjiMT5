"""backtest/job_runner.py — 回测作业子进程入口（U-E3）。

由 ue3_api 以子进程启动：python -m backtest.job_runner --spec <job.json>
作业目录 data/backtest_jobs/<job_id>/：state.json（状态机）+ result.json（结果）。

结果形状 = 前端 BacktestResult 契约（web/src/types/index.ts）。
成本语义：commission%/slippage% 按名义本金折算为每笔往返 $ 成本
（0.01 lot = 1 oz，成本$ = 入场价 × (commission%+2×slippage%)/100）。
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

LOT_OZ = 1.0                    # 0.01 lot = 1 oz


def _write(job_dir: str, name: str, payload: dict) -> None:
    with open(os.path.join(job_dir, name), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)


def _log(job_dir: str, line: str) -> None:
    state = json.load(open(os.path.join(job_dir, "state.json"), encoding="utf-8"))
    tail = state.get("log_tail", [])
    tail.append(line)
    state["log_tail"] = tail[-200:]
    _write(job_dir, "state.json", state)


def max_drawdown(equity: list[float]) -> float:
    peak, dd = float("-inf"), 0.0
    for v in equity:
        peak = max(peak, v)
        dd = max(dd, peak - v)
    return round(dd, 2)


def sharpe(per_trade_pnls: list[float]) -> float | None:
    if len(per_trade_pnls) < 2:
        return None
    mean = sum(per_trade_pnls) / len(per_trade_pnls)
    var = sum((p - mean) ** 2 for p in per_trade_pnls) / (len(per_trade_pnls) - 1)
    std = math.sqrt(var)
    return round(mean / std * math.sqrt(len(per_trade_pnls)), 2) if std > 0 else None


def run(spec: dict, job_dir: str) -> None:
    from data.parquet_store import load_ohlcv
    from backtest.followave_backtest import run_backtest, _cls_of
    import importlib

    strategy = spec["strategies"][0] if spec.get("strategies") else "m30_followave"
    tf = {"m30_followave": "M30", "m15_followave": "M15"}.get(strategy, spec.get("timeframe", "M30"))
    mod = importlib.import_module(
        "strategies.20261002_m30_followave_v1" if strategy == "m30_followave"
        else "strategies.20261002_m15_followave_v1")
    cls = _cls_of(mod)

    _log(job_dir, f"加载数据 {tf} …")
    df = load_ohlcv(spec.get("symbol", "XAUUSD"), tf)
    if spec.get("start_date"):
        df = df[df["time"] >= int(datetime_iso_ts(spec["start_date"]))]
    if spec.get("end_date"):
        df = df[df["time"] <= int(datetime_iso_ts(spec["end_date"])) + 86399]
    if len(df) < 60:
        raise RuntimeError(f"数据不足（{len(df)} 根）")

    _log(job_dir, f"回测 {strategy} on {tf}（{len(df)} 根）…")
    # 成本：名义本金百分比 → 每笔往返 $（按均价折算）
    mean_price = float(df["close"].mean())
    pct_cost = (float(spec.get("commission") or 0) + 2 * float(spec.get("slippage") or 0)) / 100
    spread_cost = round(mean_price * pct_cost, 4)

    summary, trades = run_backtest(df.copy(), cls, f"{strategy}-{tf}", spread=spread_cost)

    _log(job_dir, f"完成：{summary['n_kept']} 笔，净利 {summary['net']}")
    times = df["time"].tolist()
    initial = float(spec.get("initial_cash") or 10000)

    bt_trades, eq_vals = [], []
    cum = initial
    for t in sorted(trades, key=lambda x: x.exit_idx):
        cum += t.pnl
        eq_vals.append(round(cum, 2))
        bt_trades.append({
            "entry_time": iso(times, t.entry_idx) if t.entry_idx < len(times) else "",
            "exit_time": iso(times, t.exit_idx) if t.exit_idx < len(times) else "",
            "direction": t.direction, "entry_price": t.entry_price,
            "exit_price": t.exit_price, "pnl": t.pnl, "strategy": strategy,
            "entry_bar": t.entry_idx, "exit_bar": t.exit_idx,
            "hold_bars": t.exit_idx - t.entry_idx,
            "cum_pnl": round(cum, 2),
        })

    net = summary["net"]
    dd = max_drawdown([initial] + eq_vals) if eq_vals else 0.0
    total_return_pct = round(net / initial * 100, 2)
    pnls = [t.pnl for t in trades]

    result = {
        "total_return": net,
        "total_return_pct": total_return_pct,
        "total_trades": summary["n_kept"],
        "win_rate": summary["winrate"],
        "max_drawdown": dd,
        "sharpe_ratio": sharpe(pnls),
        "equity_curve": [{"time": int(times[min(t.exit_idx, len(times) - 1)]), "value": v}
                         for t, v in zip(sorted(trades, key=lambda x: x.exit_idx), eq_vals)],
        "trades": bt_trades,
        "by_strategy": {strategy: {
            "total_pnl": net, "total_return_pct": total_return_pct,
            "total_trades": summary["n_kept"], "max_drawdown": dd,
            "trades": bt_trades,
            "equity_curve": [{"time": 0, "value": v} for v in eq_vals],
            "sharpe": sharpe(pnls),
            "profit_loss_ratio": None,
        }},
        "version": "e-v1",
        "symbol": spec.get("symbol", "XAUUSD"),
        "timeframe": tf,
        "start_date": spec.get("start_date", ""),
        "end_date": spec.get("end_date", ""),
        "data_source": {"source": "parquet(L2)", "bars": len(df)},
        "cost": {"commission_pct": float(spec.get("commission") or 0),
                 "slippage_pct": float(spec.get("slippage") or 0),
                 "one_way_pct": float(spec.get("commission") or 0)},
        "spread_cost_per_trade": spread_cost,
        "ex_riding_excluded": summary["n_riders"],
    }
    _write(job_dir, "result.json", result)


def iso(times, idx: int) -> str:
    from datetime import datetime, timezone
    try:
        return datetime.fromtimestamp(int(times[idx]), tz=timezone.utc).isoformat()
    except Exception:
        return ""


def datetime_iso_ts(date_str: str) -> int:
    from datetime import datetime, timezone
    d = date_str.replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return int(datetime.strptime(d[:19], fmt).replace(tzinfo=timezone.utc).timestamp())
        except ValueError:
            continue
    return 0


def datetime_iso_str(times, idx: int) -> str:
    from datetime import datetime, timezone
    try:
        return datetime.fromtimestamp(int(times[idx]), tz=timezone.utc).isoformat()
    except Exception:
        return ""


def datetime_iso_str_exit(ts: int) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    args = ap.parse_args()
    job_dir = os.path.dirname(args.spec)
    spec = json.load(open(args.spec, encoding="utf-8"))
    try:
        run(spec, job_dir)
        state = json.load(open(os.path.join(job_dir, "state.json"), encoding="utf-8"))
        state.update({"status": "completed", "phase": "done",
                      "completed_at": datetime_iso_str_exit(time.time())})
        _write(job_dir, "state.json", state)
        return 0
    except Exception as e:
        state = json.load(open(os.path.join(job_dir, "state.json"), encoding="utf-8"))
        state.update({"status": "failed", "phase": "failed", "error": str(e)[:300]})
        _write(job_dir, "state.json", state)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
