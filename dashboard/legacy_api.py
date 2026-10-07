"""dashboard/legacy_api.py — U-E1 REST 端点（旧前端契约形状，docs/API_CONTRACT.md 家族 1-5）。

响应形状以旧后端为准（前端零改动优先）：
- /api/account、/api/positions、/api/market/price、/api/market/candles、
  /api/engine/status、/api/logs、/api/trades/history、/api/trades/stats
数据源：mt5_client（终端实时）+ 本地 DB（trades/ohlcv）+ logs/engine.log。
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from config import settings
from config.settings import local_dt
from data import database as db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

_mt5c = None


def get_client():
    """惰性单例（函数/变量不同名——旧版同名自遮挡 bug 的教训）。"""
    global _mt5c
    if _mt5c is None:
        from core.mt5_client import MT5Client
        _mt5c = MT5Client()
        try:
            _mt5c.connect()
        except Exception:
            _mt5c = None
            return None
    return _mt5c


def _specs():
    return _client().symbol_spec(settings.SYMBOL)


# ── 账户（家族 4）────────────────────────────────────────────
@router.get("/account")
def api_account():
    c = get_client()
    if c is None:
        raise HTTPException(503, "终端不可达")
    return c.account_summary()          # 已含 AccountInfo 契约字段


# ── 持仓（家族 1）────────────────────────────────────────────
@router.get("/positions")
def api_positions():
    c = get_client()
    if c is None:
        raise HTTPException(503, "终端不可达")
    out = c.positions_open(settings.SYMBOL)
    for p in out:
        p["is_paper"] = False
        if not p["current_price"]:
            p["current_price"] = p["price_open"]
    return out


@router.post("/positions/{ticket}/close")
def api_positions_close(ticket: int, body: dict | None = None):
    """平仓（全/部分）。写操作：journal 留痕由引擎 _on_position_gone 兜底同步。"""
    c = get_client()
    if c is None:
        raise HTTPException(503, "终端不可达")
    body = body or {}
    volume = float(body.get("volume") or 0) or None
    positions = c.positions_open(settings.SYMBOL)
    target = next((p for p in positions if p["ticket"] == ticket), None)
    if target is None:
        raise HTTPException(404, f"持仓 {ticket} 不存在")
    r = c.close_position(settings.SYMBOL, ticket, target["type"],
                         volume or target["volume"], magic=target["magic"])
    return {"ok": True, **r}


@router.post("/positions/{ticket}/modify")
def api_positions_modify(ticket: int, body: dict):
    c = get_client()
    if c is None:
        raise HTTPException(503, "终端不可达")
    r = c.modify_position_sltp(settings.SYMBOL, ticket,
                               float(body.get("sl") or 0), float(body.get("tp") or 0))
    return {"ok": True, **r}


# ── 行情（家族 3）────────────────────────────────────────────
@router.get("/market/price")
def api_market_price():
    c = get_client()
    if c is None:
        raise HTTPException(503, "终端不可达")
    t = c.get_tick(settings.SYMBOL)
    return {"bid": t["bid"], "ask": t["ask"],
            "spread": round(t["ask"] - t["bid"], 2), "symbol": settings.SYMBOL}


@router.get("/market/candles")
def api_market_candles(timeframe: str = "H1", count: int = 100, before: int | None = None):
    """K 线（显示层）。

    - 常规加载/轮询（无 before）→ **直连 MT5 实时取数**（与顶栏现价同源）：
      L1 库只有引擎策略池周期（M15/M30）被持续维护，其余周期会停在最近一次
      回填，图表曾因此显示 5 天前的旧 K 线。server 时间经 to_utc 转 UTC。
    - 历史滚动加载（带 before）→ 走 L1 只读库（深历史完整且不变）。
    - 终端不可达/offset 未校准 → 回退 L1 只读库（显示层降级；fail-closed
      纪律只约束门禁路径，图表允许优雅降级）。
    """
    if timeframe not in settings.TIMEFRAMES:
        raise HTTPException(400, f"非法周期 {timeframe}")
    n = min(max(count, 10), 5000)

    def _from_db(before_ts: int | None) -> list:
        ro = db.readonly_connect()
        try:
            if before_ts:
                rows = ro.execute(
                    "SELECT timestamp, open, high, low, close, volume FROM ohlcv"
                    " WHERE timeframe=? AND timestamp<? ORDER BY timestamp DESC LIMIT ?",
                    (timeframe, before_ts, n)).fetchall()
            else:
                rows = ro.execute(
                    "SELECT timestamp, open, high, low, close, volume FROM ohlcv"
                    " WHERE timeframe=? ORDER BY timestamp DESC LIMIT ?",
                    (timeframe, n)).fetchall()
        finally:
            ro.close()
        return [{"time": int(r[0]), "open": r[1], "high": r[2], "low": r[3],
                 "close": r[4], "volume": r[5]} for r in reversed(rows)]

    if before:
        return _from_db(int(before))

    try:
        client = get_client()
        if client is None:
            raise RuntimeError("MT5 终端不可达")
        rates = client.copy_rates(settings.SYMBOL, timeframe, n)
        # 末根是 forming bar（bar0）——显示层与行情软件一致，保留
        return [{"time": client.to_utc(int(r["time"])), "open": r["open"],
                 "high": r["high"], "low": r["low"], "close": r["close"],
                 "volume": r["volume"]} for r in rates]
    except Exception as e:
        logger.warning("[market] %s 实时 K 线失败（%s），回退 L1 只读库", timeframe, e)
        return _from_db(None)


# ── 引擎状态（家族 6 只读部分）───────────────────────────────
@router.get("/engine/status")
def api_engine_status():
    hb = os.path.join(settings.LOG_DIR, "heartbeat.txt")
    alive = False
    age = None
    try:
        age = int(time.time() - os.path.getmtime(hb))
        alive = age < 300
    except OSError:
        pass
    return {"status": "running" if alive else "stopped",
            "uptime_seconds": age or 0,          # TODO: 引擎写 started_at 后给真实 uptime
            "bridge_connected": alive}


# ── 日志（家族 6 只读部分）───────────────────────────────────
@router.get("/logs")
def api_logs(level: str | None = None, limit: int = 100, since: str | None = None):
    path = os.path.join(settings.LOG_DIR, "engine.log")
    out = []
    if os.path.exists(path):
        with open(path, encoding="utf-8", errors="ignore") as f:
            lines = f.read().splitlines()[-2000:]
        for ln in reversed(lines):
            try:
                ts, lvl, name = ln.split(" ", 2)[0], ln.split(" ")[1], ln.split(" ", 3)[2]
                msg = ln.split(" ", 3)[3] if len(ln.split(" ", 3)) > 3 else ""
            except (ValueError, IndexError):
                continue
            if level and lvl != level.upper():
                continue
            out.append({"timestamp": ts, "level": lvl, "name": name, "message": msg})
            if len(out) >= min(limit, 500):
                break
    return {"logs": out}


# ── 历史成交 + stats（家族 5）────────────────────────────────
def _row_to_closed_trade(r) -> dict:
    return {
        "ticket": int(r["position_ticket"]), "symbol": settings.SYMBOL,
        "order_type": r["direction"], "volume": r["volume"],
        "entry_price": r["entry_price"], "exit_price": r["exit_price"],
        "pnl": r["pnl"], "stop_loss": r["sl"] or 0, "take_profit": r["tp"] or 0,
        "swap": 0.0, "commission": 0.0, "magic": int(r["magic"]),
        "strategy": r["strategy"],
        "open_time": local_dt(r["open_ts"]).strftime("%Y-%m-%d %H:%M:%S") if r["open_ts"] else "",
        "close_time": local_dt(r["close_ts"]).strftime("%Y-%m-%d %H:%M:%S") if r["close_ts"] else "",
        "hold_seconds": r["hold_seconds"] or 0,
        "exit_reason": r["exit_reason"] or "", "mode": r["mode"] or "",
    }


@router.get("/trades/history")
def api_trades_history(limit: int = 100, offset: int = 0, mode: str | None = None):
    ro = db.readonly_connect()
    try:
        where, args = "WHERE close_ts IS NOT NULL", []
        if mode:
            where += " AND mode=?"
            args.append(mode)
        total = ro.execute(f"SELECT COUNT(*) FROM trades {where}", args).fetchone()[0]
        rows = ro.execute(
            f"SELECT * FROM trades {where} ORDER BY close_ts DESC LIMIT ? OFFSET ?",
            (*args, min(max(limit, 1), 999), int(offset))).fetchall()
    finally:
        ro.close()
    trades = [_row_to_closed_trade(r) for r in rows]
    return {"trades": trades, "total": total}


@router.get("/trades/stats")
def api_trades_stats():
    """MT4 标准报表口径（StrategyStats 契约字段），summary + by_magic + by_strategy。"""
    ro = db.readonly_connect()
    try:
        rows = ro.execute(
            "SELECT strategy, magic, direction, volume, pnl, 0 AS commission,"
            " 0 AS swap, hold_seconds FROM trades WHERE close_ts IS NOT NULL"
            " AND pnl IS NOT NULL ORDER BY close_ts").fetchall()
    finally:
        ro.close()

    def stats(rs):
        pnls = [float(r["pnl"] or 0) for r in rs]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        longs = [float(r["pnl"] or 0) for r in rs if r["direction"] == "BUY"]
        shorts = [float(r["pnl"] or 0) for r in rs if r["direction"] == "SELL"]
        gp, gl = sum(wins), -sum(losses)
        # 最大连亏/连盈（按时间序）
        mw = ml = cw = cl = 0
        mp = ml_pnl = 0.0
        for p in pnls:
            if p > 0:
                cw, cl = cw + 1, 0
                mw = max(mw, cw)
            elif p < 0:
                cl, cw = cl + 1, 0
                ml = max(ml, cl)
        return {
            "total_net_profit": round(sum(pnls), 2),
            "gross_profit": round(gp, 2), "gross_loss": round(gl, 2),
            "profit_factor": round(gp / gl, 2) if gl > 0 else "N/A",
            "expected_payoff": round(sum(pnls) / len(pnls), 2) if pnls else 0,
            "total_trades": len(pnls),
            "short_trades": len(shorts),
            "short_won": sum(1 for p in shorts if p > 0),
            "short_won_pct": round(sum(1 for p in shorts if p > 0) / len(shorts) * 100, 1) if shorts else 0,
            "long_trades": len(longs),
            "long_won": sum(1 for p in longs if p > 0),
            "long_won_pct": round(sum(1 for p in longs if p > 0) / len(longs) * 100, 1) if longs else 0,
            "profit_trades": len(wins), "loss_trades": len(losses),
            "win_rate": round(len(wins) / len(pnls) * 100, 1) if pnls else 0,
            "largest_profit_trade": round(max(wins), 2) if wins else 0,
            "largest_loss_trade": round(min(losses), 2) if losses else 0,
            "avg_profit_trade": round(gp / len(wins), 2) if wins else 0,
            "avg_loss_trade": round(-gl / len(losses), 2) if losses else 0,
            "ratio_avg_profit_loss": round((gp / len(wins)) / (gl / len(losses)), 2)
                if wins and losses else 0,
            "avg_hold_seconds": int(sum(int(r["hold_seconds"] or 0) for r in rs) / len(rs)) if rs else 0,
            "max_consecutive_wins": mw, "max_consecutive_losses": ml,
            "max_consecutive_wins_pnl": 0, "max_consecutive_losses_pnl": 0,
            "total_commission": round(sum(float(r["commission"] or 0) for r in rs), 2),
            "total_swap": round(sum(float(r["swap"] or 0) for r in rs), 2),
        }

    summary = stats(rows)
    by_magic, by_strategy = {}, {}
    seen: dict[tuple, list] = {}
    for r in rows:
        seen.setdefault((int(r["magic"]), r["strategy"]), []).append(r)
    for (magic, strategy), rs in seen.items():
        s = stats(rs)
        by_magic[str(magic)] = {**s, "magic": magic, "strategy": strategy}
        by_strategy[strategy] = {**s}
    return {"summary": summary, "by_magic": by_magic, "by_strategy": by_strategy}
