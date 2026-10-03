"""dashboard/queries.py — 监控面板只读数据层。

纪律（UI_APP_PLAN §6）：只读。DB 一律 readonly_connect；终端只做读调用。
任何查询失败都优雅降级（返回 None/空），面板永不因数据源问题崩掉。
"""

from __future__ import annotations

import json
import os
import time
from datetime import timedelta
from typing import Optional

from config import settings
from config.settings import local_dt
from data import database as db

_HEARTBEAT_PATH = os.path.join(settings.LOG_DIR, "heartbeat.txt")
_mt5_client = None


def engine_alive() -> dict:
    try:
        age = int(time.time() - os.path.getmtime(_HEARTBEAT_PATH))
        return {"age_s": age, "alive": age < 300}
    except OSError:
        return {"age_s": None, "alive": False}


def _get_client():
    global _mt5_client
    if _mt5_client is None:
        from core.mt5_client import MT5Client
        _mt5_client = MT5Client()
        try:
            _mt5_client.connect()
        except Exception:
            _mt5_client = None
            return None
    return _mt5_client


def account() -> Optional[dict]:
    client = _get_client()
    if client is None:
        return None
    try:
        return client.account_summary()
    except Exception:
        return None


def magic_map(conn) -> dict[int, str]:
    rows = conn.execute(
        "SELECT magic, strategy FROM signals GROUP BY magic, strategy"
        " ORDER BY MAX(id) DESC").fetchall()
    m: dict[int, str] = {}
    for magic, name in rows:
        m.setdefault(int(magic), name)
    return m


def positions_view() -> Optional[list[dict]]:
    """当前持仓（含策略名映射），终端不可达 → None。"""
    client = _get_client()
    if client is None:
        return None
    try:
        positions = client.positions_open(settings.SYMBOL)
    except Exception:
        return None
    conn = db.readonly_connect()
    try:
        mmap = magic_map(conn)
    finally:
        conn.close()
    for p in positions:
        p["strategy"] = mmap.get(p["magic"], f"magic:{p['magic']}")
        p["open_local"] = local_dt(p["time"]).strftime("%m-%d %H:%M")
        p["hold_min"] = int((settings.utc_now() - p["time"]) / 60)
    return positions


def day_week_pnl() -> dict:
    now = settings.utc_now()
    import datetime as _dt
    weekday = _dt.datetime.fromtimestamp(now, tz=_dt.timezone.utc).weekday()
    today0 = int(now) // 86400 * 86400
    week0 = today0 - weekday * 86400
    try:
        ro = db.readonly_connect()
        day = ro.execute("SELECT COALESCE(SUM(pnl),0) FROM trades WHERE close_ts >= ?",
                         (today0,)).fetchone()[0]
        week = ro.execute("SELECT COALESCE(SUM(pnl),0) FROM trades WHERE close_ts >= ?",
                          (week0,)).fetchone()[0]
        ro.close()
        return {"day": round(float(day), 2), "week": round(float(week), 2)}
    except Exception:
        return {"day": None, "week": None}


def _fmt_ts(ts) -> str:
    return local_dt(int(ts)).strftime("%m-%d %H:%M:%S") if ts else "-"


def signals_tail(limit: int = 100) -> list[dict]:
    ro = db.readonly_connect()
    try:
        rows = ro.execute(
            "SELECT id, created_ts, strategy, timeframe, direction, status,"
            " exit_reason, score_long, score_short FROM signals"
            " ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    finally:
        ro.close()
    return [{"id": r[0], "time": _fmt_ts(r[1]), "strategy": r[2], "tf": r[3],
             "direction": r[4] or "-", "status": r[5], "exit_reason": r[6] or "",
             "score": f"{r[7]}/{r[8]}"} for r in rows]


def trades_tail(limit: int = 50) -> list[dict]:
    ro = db.readonly_connect()
    try:
        rows = ro.execute(
            "SELECT position_ticket, strategy, direction, volume, entry_price,"
            " exit_price, pnl, pnl_source, exit_reason, close_ts FROM trades"
            " WHERE close_ts IS NOT NULL ORDER BY close_ts DESC LIMIT ?", (limit,)).fetchall()
    finally:
        ro.close()
    return [{"ticket": r[0], "strategy": r[1], "direction": r[2], "volume": r[3],
             "entry": r[4], "exit": r[5], "pnl": r[6], "src": r[7] or "-",
             "reason": r[8] or "", "close": _fmt_ts(r[9])} for r in rows]


def gate_stats(hours: int = 24) -> list[dict]:
    since = int(settings.utc_now()) - hours * 3600
    ro = db.readonly_connect()
    try:
        rows = ro.execute(
            "SELECT exit_reason, COUNT(*) FROM signals WHERE status='voided'"
            " AND created_ts >= ? GROUP BY exit_reason ORDER BY 2 DESC",
            (since,)).fetchall()
    finally:
        ro.close()
    out = []
    for reason, n in rows:
        gate = reason.split(":", 1)[0] if reason else "?"
        out.append({"gate": gate, "reason": reason, "count": n})
    return out


def journal_tail(n: int = 20) -> list[dict]:
    path = os.path.join(settings.JOURNAL_DIR, "closed_trades.jsonl")
    if not os.path.exists(path):
        return []
    lines = open(path, encoding="utf-8").read().strip().splitlines()[-n:]
    out = []
    for ln in reversed(lines):
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out


def market_open_now() -> bool:
    from engine.risk import gatekeeper as gk
    return not gk.g5_market_open({"now": settings.utc_now()}).blocked


def risk_overview() -> list[dict]:
    """G0~G15 当前状态一览。能算的算，不能算的标 '—'（诚实展示）。"""
    pnl = day_week_pnl()
    day, week = pnl["day"], pnl["week"]
    positions = positions_view() or []
    n_total = len(positions)
    balance = (account() or {}).get("balance")
    P = settings.RISK_PARAMS

    def pct(pnl_v):
        return (abs(pnl_v) / balance * 100) if (balance and pnl_v is not None) else None

    day_pct, week_pct = pct(day), pct(week)
    rows = []
    g0 = os.path.exists(settings.SAFETY_LOCK_PATH)
    rows.append(("G0", "安全急停", "拦截" if g0 else "放行",
                 "锁文件存在" if g0 else "无锁"))
    rows.append(("G1", "新闻黑屏", "未配置", "日历未接入（放行）"))
    rows.append(("G2", "新闻偏向", "未配置", "配置默认关"))
    if day is None:
        rows.append(("G3", "日亏 12%", "—", "无成交数据"))
    else:
        hit = day < 0 and day_pct >= P["max_daily_loss_pct"]
        rows.append(("G3", "日亏 12%", "拦截" if hit else "放行",
                     f"今日 {day:+.2f}（{day_pct:.1f}%）"))
    if week is None:
        rows.append(("G3b", "周回撤 15%", "—", "无成交数据"))
    else:
        hit = week < 0 and week_pct >= P["weekly_max_drawdown_pct"]
        rows.append(("G3b", "周回撤 15%", "拦截" if hit else "放行",
                     f"本周 {week:+.2f}（{week_pct:.1f}%）"))
    rows.append(("G4", "浮亏 10%", "—", "按策略评估，随持仓显示"))
    mo = market_open_now()
    rows.append(("G5", "市场开市", "放行" if mo else "拦截",
                 "开市中" if mo else "休市时段"))
    rows.append(("G6", "实亏封锁", "—", "状态机随平仓更新"))
    rows.append(("G7", "连亏 3×4h", "—", "状态机随平仓更新"))
    rows.append(("G8", "急速出场 2h", "—", "状态机随平仓更新"))
    per_max = max((sum(1 for p in positions if p["magic"] == m)
                   for m in {p["magic"] for p in positions}), default=0)
    rows.append(("G9", "单策略并发=1", "拦截" if per_max >= P["per_strategy_max_positions"]
                 and positions else "放行", f"最大单策略持仓 {per_max}"))
    rows.append(("G9b", "账户并发≤6", "拦截" if n_total >= P["max_total_positions"]
                 else "放行", f"合计 {n_total}/{P['max_total_positions']}"))
    rows.append(("G10", "同向浮亏禁加仓", "—", "随信号评估"))
    rows.append(("G11", "盈利冷却 2h", "—", "随平仓更新"))
    rows.append(("G12", "K 线门禁", "—", "宿主在策略"))
    rows.append(("G13", "方向过滤", "放行" if settings.GLOBAL_DIRECTION_FILTER == "BOTH"
                 else settings.GLOBAL_DIRECTION_FILTER, ""))
    rows.append(("G14", "MTF 共振", "未配置" if not settings.MTF_RESONANCE_ENABLED else "启用", ""))
    rows.append(("G15", "3-tick 复核", "—", "执行轨（Athlete）"))
    return [{"id": i, "name": n, "state": s, "detail": d} for i, n, s, d in rows]


def latest_shadow_report() -> Optional[str]:
    rdir = os.path.join(settings.REPO_ROOT, "docs", "reports")
    if not os.path.isdir(rdir):
        return None
    files = sorted(f for f in os.listdir(rdir) if f.startswith("shadow_weekly_"))
    if not files:
        return None
    path = os.path.join(rdir, files[-1])
    return open(path, encoding="utf-8").read()


# ── 图表数据（v2：ECharts 可视化）───────────────────────────

def candles(tf: str = "M30", limit: int = 200) -> list[dict]:
    if tf not in settings.TIMEFRAMES:
        raise ValueError(tf)
    ro = db.readonly_connect()
    try:
        rows = ro.execute(
            "SELECT timestamp, open, high, low, close, volume FROM ohlcv"
            " WHERE timeframe=? ORDER BY timestamp DESC LIMIT ?",
            (tf, limit)).fetchall()
    finally:
        ro.close()
    return [{"time": r[0], "open": r[1], "high": r[2], "low": r[3],
             "close": r[4], "volume": r[5]} for r in reversed(rows)]


def equity_curve() -> list[dict]:
    """已实现累计盈亏曲线（trades 依平仓时间累加）。"""
    ro = db.readonly_connect()
    try:
        rows = ro.execute(
            "SELECT close_ts, pnl FROM trades WHERE close_ts IS NOT NULL"
            " AND pnl IS NOT NULL ORDER BY close_ts").fetchall()
    finally:
        ro.close()
    cum, out = 0.0, []
    for ts, pnl in rows:
        cum += float(pnl or 0.0)
        out.append({"time": int(ts), "cum": round(cum, 2)})
    return out


def trade_pnls(limit: int = 50) -> list[dict]:
    ro = db.readonly_connect()
    try:
        rows = ro.execute(
            "SELECT close_ts, strategy, pnl FROM trades WHERE close_ts IS NOT NULL"
            " AND pnl IS NOT NULL ORDER BY close_ts DESC LIMIT ?", (limit,)).fetchall()
    finally:
        ro.close()
    return [{"time": _fmt_ts(r[0]), "strategy": r[1], "pnl": round(float(r[2] or 0), 2)}
            for r in reversed(rows)]


def daily_pnl(days: int = 30) -> list[dict]:
    """按 UTC+8 自然日聚合的已实现盈亏。"""
    since = int(settings.utc_now()) - days * 86400
    ro = db.readonly_connect()
    try:
        rows = ro.execute(
            "SELECT close_ts, pnl FROM trades WHERE close_ts >= ? AND pnl IS NOT NULL",
            (since,)).fetchall()
    finally:
        ro.close()
    agg: dict[str, float] = {}
    for ts, pnl in rows:
        day = local_dt(int(ts)).strftime("%m-%d")
        agg[day] = agg.get(day, 0.0) + float(pnl or 0.0)
    return [{"day": k, "pnl": round(v, 2)} for k, v in sorted(agg.items())]


def shadow_daily(days: int = 14) -> dict:
    """影子对照：MT5 vs MT4 各策略每日已实现盈亏（UTC+8 日）。"""
    import datetime as _dt
    now = settings.utc_now()
    t0 = int(now) - days * 86400
    ours: dict[tuple[str, str], float] = {}
    ro = db.readonly_connect()
    try:
        rows = ro.execute(
            "SELECT close_ts, strategy, pnl FROM trades WHERE close_ts >= ?"
            " AND pnl IS NOT NULL", (t0,)).fetchall()
    finally:
        ro.close()
    for ts, strategy, pnl in rows:
        day = local_dt(int(ts)).strftime("%m-%d")
        ours[(strategy, day)] = ours.get((strategy, day), 0.0) + float(pnl or 0.0)

    old: dict[tuple[str, str], float] = {}
    try:
        from tools.mt4_overlap_check import old_db_connect
        oc = old_db_connect()
        oc.execute("PRAGMA query_only=ON")
        for strat in ("m30_followave", "m15_followave"):
            trows = oc.execute(
                "SELECT close_time, pnl FROM trades WHERE strategy=?", (strat,)).fetchall()
            for close_time, pnl in trows:
                try:
                    ct = _dt.datetime.strptime(close_time, "%Y-%m-%d %H:%M:%S").replace(
                        tzinfo=_dt.timezone(timedelta(hours=8)))
                except ValueError:
                    continue
                if int(ct.timestamp()) < t0:
                    continue
                day = ct.strftime("%m-%d")
                old[(strat, day)] = old.get((strat, day), 0.0) + float(pnl or 0.0)
        oc.close()
    except Exception:
        pass

    day_keys = sorted({d for _, d in list(ours) + list(old)})
    return {
        "days": day_keys,
        "m30_ours": [round(ours.get(("m30_followave", d), 0.0), 2) for d in day_keys],
        "m30_old": [round(old.get(("m30_followave", d), 0.0), 2) for d in day_keys],
        "m15_ours": [round(ours.get(("m15_followave", d), 0.0), 2) for d in day_keys],
        "m15_old": [round(old.get(("m15_followave", d), 0.0), 2) for d in day_keys],
    }


def tick_info() -> Optional[dict]:
    client = _get_client()
    if client is None:
        return None
    try:
        t = client.get_tick(settings.SYMBOL)
        return {"bid": t["bid"], "ask": t["ask"],
                "spread": round(t["ask"] - t["bid"], 2)}
    except Exception:
        return None
