"""dashboard/app.py — 监控面板（v1 纯只读，UI_APP_PLAN §0）。

纪律：不提供任何交易写操作；DB 只读；终端只做读调用。
启动：python tools/run_dashboard.py [--host 127.0.0.1] [--port 8800]
"""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from dashboard import queries

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)

app = FastAPI(title="神机 MT5 监控", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=os.path.join(HERE, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(HERE, "templates"))


def _f_cls(v):
    return "up" if (v or 0) > 0 else ("down" if (v or 0) < 0 else "")


def _f_sign(v):
    return "—" if v is None else f"{v:+.2f}"


templates.env.filters["cls"] = _f_cls
templates.env.filters["sign"] = _f_sign

_TOKEN = os.environ.get("DASHBOARD_TOKEN", "")


def _check_token(request: Request) -> None:
    """可选认证：设置环境变量 DASHBOARD_TOKEN 后，请求须带 ?token= 或 Cookie。"""
    if not _TOKEN:
        return
    if request.query_params.get("token") == _TOKEN:
        return
    if request.cookies.get("dashboard_token") == _TOKEN:
        return
    raise HTTPException(status_code=401, detail="token required")


@app.get("/", response_class=HTMLResponse)
def overview(request: Request):
    _check_token(request)
    return templates.TemplateResponse(request, "overview.html", _overview_ctx())


@app.get("/partials/overview", response_class=HTMLResponse)
def overview_partial(request: Request):
    _check_token(request)
    return templates.TemplateResponse(request, "_overview_body.html", _overview_ctx())


@app.get("/flows", response_class=HTMLResponse)
def flows(request: Request, limit: int = 100):
    _check_token(request)
    ctx = {
        "signals": queries.signals_tail(min(limit, 500)),
        "trades": queries.trades_tail(50),
        "gate_stats": queries.gate_stats(24),
        "journal": queries.journal_tail(20),
        "active": "flows",
    }
    return templates.TemplateResponse(request, "flows.html", ctx)


@app.get("/shadow", response_class=HTMLResponse)
def shadow(request: Request):
    _check_token(request)
    return templates.TemplateResponse(request, "shadow.html",
                                      {"report": queries.latest_shadow_report(),
                                       "active": "shadow"})


@app.get("/api/overview")
def api_overview(request: Request):
    _check_token(request)
    ctx = _overview_ctx()
    return {
        "engine": ctx["engine"],
        "account": ctx["account"],
        "pnl": ctx["pnl"],
        "positions": ctx["positions"],
        "market_open": ctx["market_open"],
        "tick": queries.tick_info(),
    }


@app.get("/api/candles")
def api_candles(request: Request, tf: str = "M30", limit: int = 200):
    _check_token(request)
    try:
        return queries.candles(tf, min(max(limit, 20), 1000))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"非法周期 {tf}")


@app.get("/api/equity")
def api_equity(request: Request):
    _check_token(request)
    return queries.equity_curve()


@app.get("/api/trade_pnls")
def api_trade_pnls(request: Request, limit: int = 50):
    _check_token(request)
    return queries.trade_pnls(min(max(limit, 10), 200))


@app.get("/api/daily_pnl")
def api_daily_pnl(request: Request, days: int = 30):
    _check_token(request)
    return queries.daily_pnl(min(max(days, 7), 180))


@app.get("/api/shadow/chart")
def api_shadow_chart(request: Request, days: int = 14):
    _check_token(request)
    return queries.shadow_daily(min(max(days, 7), 60))


def _overview_ctx() -> dict:
    acct = queries.account()
    return {
        "engine": queries.engine_alive(),
        "account": acct,
        "pnl": queries.day_week_pnl(),
        "positions": queries.positions_view() or [],
        "risk": queries.risk_overview(),
        "market_open": queries.market_open_now(),
        "active": "overview",
    }
