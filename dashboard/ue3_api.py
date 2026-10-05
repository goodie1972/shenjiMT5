"""dashboard/ue3_api.py — U-E3 端点：回测中心作业引擎 / 新闻占位 / 报告 / 信号列表。

回测 = 子进程作业（backtest/job_runner.py），作业目录 data/backtest_jobs/<id>/。
范围外（诚实占位）：新闻日历返回空日历（G1 数据源后置）；MCP/version 不做。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from config import settings
from data import database as db

router = APIRouter(prefix="/api")

REPO_ROOT = settings.REPO_ROOT
JOBS_DIR = os.path.join(settings.DATA_DIR, "backtest_jobs")
REPORTS_DIR = os.path.join(settings.DATA_DIR, "reports")
PARQUET = os.path.join(settings.DATA_DIR, "am_parquet")


# ── 回测中心 ─────────────────────────────────────────────────
def _job_dir(job_id: str) -> str:
    d = os.path.join(JOBS_DIR, job_id)
    if not os.path.isdir(d):
        raise HTTPException(404, f"作业 {job_id} 不存在")
    return d


def _read_state(job_id: str) -> dict:
    p = os.path.join(_job_dir(job_id), "state.json")
    return json.load(open(p, encoding="utf-8"))


@router.post("/backtest/run")
def api_backtest_run(body: dict):
    strategies = body.get("strategies") or []
    strategies = [s for s in strategies if s in ("m30_followave", "m15_followave")]
    if not strategies:
        raise HTTPException(422, "strategies 需含 m30_followave / m15_followave")
    # 数据覆盖（L2 parquet 范围）→ 区间自动收敛（v11 语义）
    import pandas as pd
    tf = body.get("timeframe", "M30")
    pfile = os.path.join(PARQUET, f"{body.get('symbol', 'XAUUSD')}_{tf}.parquet")
    if not os.path.exists(pfile):
        raise HTTPException(422, f"无 {tf} 数据")
    df = pd.read_parquet(pfile)
    tmin, tmax = int(df["time"].min()), int(df["time"].max())
    start = body.get("start_date") or datetime.fromtimestamp(tmin, tz=timezone.utc).strftime("%Y-%m-%d")
    end = body.get("end_date") or datetime.fromtimestamp(tmax, tz=timezone.utc).strftime("%Y-%m-%d")
    s_ts = _ts(start)
    e_ts = _ts(end) + 86399
    if s_ts > tmax or e_ts < tmin:
        raise HTTPException(422, f"请求区间与数据无交集（数据覆盖至 "
                                 f"{datetime.fromtimestamp(tmax, tz=timezone.utc):%Y-%m-%d}）")
    job_id = uuid.uuid4().hex[:12]
    jd = os.path.join(JOBS_DIR, job_id)
    os.makedirs(jd, exist_ok=True)
    spec = {"strategies": strategies, "symbol": body.get("symbol", "XAUUSD"),
            "timeframe": tf, "start_date": start, "end_date": end,
            "initial_cash": body.get("initial_cash", 10000),
            "commission": body.get("commission", 0),
            "slippage": body.get("slippage", 0)}
    _json_write(os.path.join(jd, "spec.json"), spec)
    _json_write(os.path.join(jd, "state.json"),
                {"job_id": job_id, "status": "queued", "phase": "queued",
                 "created_at": _now(), "log_tail": ["作业创建"]})
    subprocess.Popen([sys.executable, "-m", "backtest.job_runner",
                      "--spec", os.path.join(jd, "spec.json")],
                     cwd=REPO_ROOT,
                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    return {"job_id": job_id}


@router.get("/backtest/status/{job_id}")
def api_backtest_status(job_id: str):
    st = _read_state(job_id)
    st.setdefault("job_id", job_id)
    return st


@router.get("/backtest/results/{job_id}")
def api_backtest_results(job_id: str):
    jd = _job_dir(job_id)
    rp = os.path.join(jd, "result.json")
    if not os.path.exists(rp):
        raise HTTPException(404, "结果未就绪")
    result = json.load(open(rp, encoding="utf-8"))
    # K 线 + 交易标记（v7 契约）
    try:
        from data.parquet_store import load_ohlcv
        tf = result.get("timeframe", "M30")
        df = load_ohlcv(result.get("symbol", "XAUUSD"), tf)
        s = _ts(result.get("start_date") or 0)
        e = _ts(result.get("end_date") or 9e18)
        sl = df[(df["time"] >= s) & (df["time"] <= e)]
        if len(sl) > 1500:
            sl = sl.iloc[:: len(sl) // 1500 + 1]
        result["candles"] = sl.to_dict("records")
        markers = []
        for t in result.get("trades", []):
            from datetime import datetime, timezone
            for key, typ in (("entry_time", "entry"), ("exit_time", "exit")):
                try:
                    ts = int(datetime.fromisoformat(t[key]).timestamp())
                    markers.append({"time": ts, "type": typ,
                                    "side": t["direction"], "price": t[typ + "_price"]})
                except Exception:
                    continue
        result["trade_markers"] = sorted(markers, key=lambda m: m["time"])
    except Exception:
        pass
    return result


@router.get("/backtest/history")
def api_backtest_history():
    out = []
    if os.path.isdir(JOBS_DIR):
        for jid in sorted(os.listdir(JOBS_DIR)):
            sp = os.path.join(JOBS_DIR, jid, "state.json")
            rp = os.path.join(JOBS_DIR, jid, "result.json")
            if not os.path.exists(sp):
                continue
            st = json.load(open(sp, encoding="utf-8"))
            item = {"job_id": jid, "status": st.get("status"),
                    "created_at": st.get("created_at"),
                    "params": json.load(open(os.path.join(JOBS_DIR, jid, "spec.json"),
                                             encoding="utf-8"))}
            if os.path.exists(rp):
                r = json.load(open(rp, encoding="utf-8"))
                item["result_summary"] = {
                    "total_return_pct": r.get("total_return_pct"),
                    "total_trades": r.get("total_trades"),
                    "win_rate": r.get("win_rate"), "max_drawdown": r.get("max_drawdown")}
            out.append(item)
    return sorted(out, key=lambda x: x.get("created_at") or "", reverse=True)


@router.get("/backtest/strategies")
def api_backtest_strategies():
    return [
        {"name": "m30_followave", "label": "M30 FollowAve v1.0", "real": True},
        {"name": "m15_followave", "label": "M15 FollowAve v1.0", "real": True},
        {"name": "smoke", "label": "smoke（冒烟探针）", "real": True},
    ]


@router.get("/backtest/indicators")
def api_backtest_indicators():
    from strategies.base import INDICATOR_WHITELIST
    return [{"name": k, "params": {}} for k in sorted(INDICATOR_WHITELIST)]


@router.post("/backtest/formula/save")
def api_formula_save(body: dict):
    raise HTTPException(501, "公式策略生成（远期）")


@router.post("/backtest/combo/save")
def api_combo_save(body: dict):
    raise HTTPException(501, "组合策略生成（远期）")


# ── 新闻（诚实占位：G1 数据源后置）──────────────────────────
@router.get("/news/calendar")
def api_news_calendar():
    return {"is_blackout": False, "blackout_reason": "",
            "upcoming_events": [], "blackout_windows": []}


@router.get("/news/gold")
def api_news_gold():
    return {"items": [], "bias": None, "note": "新闻源未接入（G1 后置）"}


# ── 信号列表（策略雷达/信号面板）─────────────────────────────
@router.get("/signals")
def api_signals(limit: int = 50):
    ro = db.readonly_connect()
    try:
        rows = ro.execute(
            "SELECT id, created_ts, strategy, timeframe, direction, status, exit_reason"
            " FROM signals ORDER BY id DESC LIMIT ?", (min(limit, 300),)).fetchall()
    finally:
        ro.close()
    return [{"id": r[0], "time": r[1], "strategy": r[2], "timeframe": r[3],
             "direction": r[4], "status": r[5], "exit_reason": r[6]} for r in rows]


# ── 日报周报 + 影子对照（家族 10）────────────────────────────
@router.get("/reports")
def api_reports():
    out = []
    if os.path.isdir(REPORTS_DIR):
        for f in sorted(os.listdir(REPORTS_DIR), reverse=True):
            if f.endswith(".json"):
                d = json.load(open(os.path.join(REPORTS_DIR, f), encoding="utf-8"))
                out.append({"id": f[:-5], "type": d.get("type", "daily"),
                            "date": d.get("date"), "created_at": d.get("created_at")})
    return out


@router.get("/reports/{report_id}")
def api_report_detail(report_id: str):
    p = os.path.join(REPORTS_DIR, report_id + ".json")
    if not os.path.exists(p):
        raise HTTPException(404)
    return json.load(open(p, encoding="utf-8"))


@router.get("/reports/timeline/{date}")
def api_report_timeline(date: str, type: str | None = None):
    return {"items": [], "note": "时间线聚合（D7）"}


@router.post("/reports/generate")
def api_reports_generate(type: str = "daily", date: str | None = None):
    date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if type != "daily":
        raise HTTPException(422, "暂仅支持 daily")
    day0 = _ts(date)
    ro = db.readonly_connect()
    try:
        trades = ro.execute(
            "SELECT strategy, direction, pnl, exit_reason, close_ts FROM trades"
            " WHERE close_ts >= ? AND close_ts < ?", (day0, day0 + 86400)).fetchall()
        gates = ro.execute(
            "SELECT exit_reason, COUNT(*) FROM signals WHERE status='voided'"
            " AND created_ts >= ? AND created_ts < ? GROUP BY exit_reason",
            (day0, day0 + 86400)).fetchall()
    finally:
        ro.close()
    pnls = [float(r[2] or 0) for r in trades]
    report = {
        "id": f"daily_{date}", "type": "daily", "date": date,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "kpi": {"trades": len(pnls), "net": round(sum(pnls), 2),
                "wins": sum(1 for p in pnls if p > 0),
                "gate_blocks": sum(g[1] for g in gates)},
        "trades": [{"strategy": r[0], "direction": r[1], "pnl": r[2],
                    "exit_reason": r[3]} for r in trades],
        "gate_blocks": [{"reason": g[0], "count": g[1]} for g in gates],
    }
    os.makedirs(REPORTS_DIR, exist_ok=True)
    _json_write(os.path.join(REPORTS_DIR, f"daily_{date}.json"), report)
    return report


def _ts(date_str: str) -> int:
    from datetime import datetime, timezone
    d = date_str.replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return int(datetime.strptime(d[:10] if len(d) == 10 else d[:19], fmt)
                       .replace(tzinfo=timezone.utc).timestamp())
        except ValueError:
            continue
    return 0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_write(path: str, payload: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
