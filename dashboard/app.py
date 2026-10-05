"""dashboard/app.py — FastAPI 应用。

两条 UI 前端共用一个后端（/api 与 /ws）：
- 根路径 `/`      ：fork 的旧前端 SPA（web/dist，用户选定的 E 路线底座；需先 npm run build）
- `/v2/*`         ：v2 HTMX 监控页（内部工具；总览/流水/影子）
- `/api/*`        ：U-E1 legacy REST（旧前端契约形状）+ v2 面板 JSON
- `/ws`           ：WS hub（prices/positions/account/logs 通道）

token 认证：设环境变量 DASHBOARD_TOKEN 后启用（?token= 或 Cookie）。
"""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from dashboard import queries
from dashboard.legacy_api import router as legacy_router
from dashboard.ue2_api import router as ue2_router
from dashboard.ue3_api import router as ue3_router

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
WEB_DIST = os.path.join(REPO_ROOT, "web", "dist")
HAS_WEB_DIST = os.path.exists(os.path.join(WEB_DIST, "index.html"))

app = FastAPI(title="神机 MT5", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=os.path.join(HERE, "static")), name="static")
if HAS_WEB_DIST:
    app.mount("/assets", StaticFiles(directory=os.path.join(WEB_DIST, "assets")), name="spa-assets")
templates = Jinja2Templates(directory=os.path.join(HERE, "templates"))


def _f_cls(v):
    return "up" if (v or 0) > 0 else ("down" if (v or 0) < 0 else "")


def _f_sign(v):
    return "—" if v is None else f"{v:+.2f}"


templates.env.filters["cls"] = _f_cls
templates.env.filters["sign"] = _f_sign

# ── legacy API（U-E1：旧前端契约形状）────────────────────────
app.include_router(legacy_router)
app.include_router(ue2_router)
app.include_router(ue3_router)

# ── token 认证（可选）────────────────────────────────────────
_TOKEN = os.environ.get("DASHBOARD_TOKEN", "")


def _check_token(request: Request) -> None:
    if not _TOKEN:
        return
    if request.query_params.get("token") == _TOKEN:
        return
    if request.cookies.get("dashboard_token") == _TOKEN:
        return
    raise HTTPException(status_code=401, detail="token required")


# ── WS hub ───────────────────────────────────────────────────
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    from dashboard import wshub
    import asyncio
    await wshub.register(ws)
    if not getattr(wshub, "_task_started", False):
        wshub._task_started = True
        asyncio.create_task(wshub.broadcaster())
    try:
        while True:
            await ws.receive_text()            # 保活；断开时抛 WebSocketDisconnect
    except Exception:
        pass
    finally:
        wshub.unregister(ws)


# ── v2 HTMX 监控页（内部工具；前缀 /v2）────────────────────
@app.get("/v2", response_class=HTMLResponse, include_in_schema=False)
def v2_overview(request: Request):
    _check_token(request)
    return templates.TemplateResponse(request, "overview.html", _overview_ctx())


@app.get("/v2/partials/overview", response_class=HTMLResponse, include_in_schema=False)
def v2_overview_partial(request: Request):
    _check_token(request)
    return templates.TemplateResponse(request, "_overview_body.html", _overview_ctx())


@app.get("/v2/flows", response_class=HTMLResponse, include_in_schema=False)
def v2_flows(request: Request, limit: int = 100):
    _check_token(request)
    ctx = {
        "signals": queries.signals_tail(min(limit, 500)),
        "trades": queries.trades_tail(50),
        "gate_stats": queries.gate_stats(24),
        "journal": queries.journal_tail(20),
        "active": "flows",
    }
    return templates.TemplateResponse(request, "flows.html", ctx)


@app.get("/v2/shadow", response_class=HTMLResponse, include_in_schema=False)
def v2_shadow(request: Request):
    _check_token(request)
    return templates.TemplateResponse(request, "shadow.html",
                                      {"report": queries.latest_shadow_report(),
                                       "active": "shadow"})


# ── v2 面板 JSON ─────────────────────────────────────────────
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


# ── fork 前端 SPA（根路径；history 回退）────────────────────
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def spa_index():
    if HAS_WEB_DIST:
        return HTMLResponse(open(os.path.join(WEB_DIST, "index.html"),
                                 encoding="utf-8").read())
    return templates.TemplateResponse(request, "overview.html", _overview_ctx())


@app.get("/{spa_path:path}", response_class=HTMLResponse, include_in_schema=False)
def spa_fallback(spa_path: str, request: Request):
    """非 API/非 /v2/非 /static 的未知路径 → SPA（history 回退）；其余 404。"""
    if spa_path.startswith(("api/", "ws", "static/", "assets/", "v2/", "docs/")):
        raise HTTPException(404)
    full = os.path.join(WEB_DIST, spa_path)
    if HAS_WEB_DIST and os.path.isfile(full):
        ext = os.path.splitext(full)[1]
        ctype = {".js": "text/javascript", ".css": "text/css", ".png": "image/png",
                 ".svg": "image/svg+xml", ".html": "text/html", ".ico": "image/x-icon",
                 ".webmanifest": "application/json"}.get(ext, "application/octet-stream")
        return HTMLResponse(open(full, "rb").read(), media_type=ctype)
    if HAS_WEB_DIST:
        return spa_index()
    raise HTTPException(404)


