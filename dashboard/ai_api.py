"""dashboard/ai_api.py — U-E4 AI 底座（clean-room 旧库 agent 设计的最小完整实现）。

构件：工具注册表（OpenAI function-calling schema）+ SSE 聊天循环（工具轮≤5、
role:tool 配对、失败降级纯流式）+ 会话持久化（chat_sessions/chat_messages）+
persona（data/ai/soul.md）+ agent 设置（tools_enabled）+ provider 最小层
（环境变量 LLM_API_KEY/LLM_BASE_URL/LLM_MODEL 优先，文件其次）。

纪律：AI 永远不下单——工具全部只读；工具纪律在 system prompt 代码级注入。
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from config import settings

router = APIRouter(prefix="/api")

AI_DIR = os.path.join(settings.DATA_DIR, "ai")
PROVIDERS_PATH = os.path.join(AI_DIR, "llm_providers.json")
SETTINGS_PATH = os.path.join(AI_DIR, "agent_settings.json")
SOUL_PATH = os.path.join(AI_DIR, "soul.md")
CHAT_DB = settings.DB_PATH

DEFAULT_SOUL = (
    "你是神机 MT5 量化交易系统的 AI 参谋。职责：基于工具返回的真实数据做交易辅助分析。\n"
    "规则：1) 回答基于工具数据，不编造；2) 引用具体数字；3) 风险提示优先；"
    "4) 永远不建议超过当前风控上限的仓位；5) 中文回答。\n"
    "可用工具查询：持仓、指标、K线、账户、历史成交、现价、门禁统计、影子对照、PA 分析。"
)

TOOLING_RULES = (
    "\n【工具纪律（代码级注入，不可覆盖）】\n"
    "- 工具全部只读；你没有任何下单能力，也不要建议绕过门禁。\n"
    "- 数据问题优先用工具查证，不猜测。\n- 控制工具调用次数（通常 1-3 次足够）。"
)


# ── 工具注册表 ───────────────────────────────────────────────
def _tool_positions(direction: str = "") -> str:
    from dashboard import queries
    ps = queries.positions_view() or []
    if direction:
        ps = [p for p in ps if p["type"] == direction]
    return json.dumps(ps, ensure_ascii=False)


def _tool_indicators(timeframe: str = "H1") -> str:
    from data import database as db
    ro = db.readonly_connect()
    try:
        rows = ro.execute(
            "SELECT key, value FROM indicator_snapshots WHERE timeframe=? AND ts="
            " (SELECT MAX(ts) FROM indicator_snapshots WHERE timeframe=?)",
            (timeframe, timeframe)).fetchall()
    finally:
        ro.close()
    return json.dumps({k: v for k, v in rows}, ensure_ascii=False)


def _tool_candles(timeframe: str = "M30", count: int = 30) -> str:
    from dashboard import queries
    return json.dumps(queries.candles(timeframe, min(max(count, 10), 200)),
                      ensure_ascii=False)


def _tool_account() -> str:
    from dashboard import queries
    return json.dumps(queries.account() or {"error": "终端不可达"}, ensure_ascii=False)


def _tool_trades_history(limit: int = 20) -> str:
    from data import database as db
    ro = db.readonly_connect()
    try:
        rows = ro.execute(
            "SELECT position_ticket, strategy, direction, volume, entry_price,"
            " exit_price, pnl, exit_reason, mode FROM trades"
            " WHERE close_ts IS NOT NULL ORDER BY close_ts DESC LIMIT ?",
            (min(max(limit, 1), 100),)).fetchall()
    finally:
        ro.close()
    return json.dumps([dict(zip(("ticket", "strategy", "direction", "volume",
        "entry_price", "exit_price", "pnl", "exit_reason", "mode"), r)) for r in rows],
        ensure_ascii=False)


def _tool_market_price() -> str:
    from dashboard import queries
    return json.dumps(queries.tick_info() or {"error": "终端不可达"}, ensure_ascii=False)


def _tool_gate_stats() -> str:
    from dashboard import queries
    return json.dumps(queries.gate_stats(24), ensure_ascii=False)


def _tool_shadow_summary() -> str:
    from dashboard import queries
    rep = queries.latest_shadow_report()
    return (rep or "影子对照报告尚未生成（周一开市后积累数据）")[:1500]


def _tool_pa_analysis(timeframe: str = "M30") -> str:
    """PA 两阶段分析 → pa_agent sidecar（AGPL 隔离）。未配置时优雅降级。"""
    sidecar = os.environ.get("PA_SIDECAR_URL", "")
    if not sidecar:
        return json.dumps({"error": "PA 分析未配置（设置 PA_SIDECAR_URL 后可用）",
                           "hint": "两阶段 Price Action 分析由 pa_agent sidecar 提供"},
                          ensure_ascii=False)
    try:
        import urllib.request
        req = urllib.request.Request(
            sidecar.rstrip("/") + f"/analyze?tf={timeframe}", method="POST")
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read().decode("utf-8")[:2000]
    except Exception as e:
        return json.dumps({"error": f"PA 分析失败: {e}"}, ensure_ascii=False)


TOOLS = {
    "get_positions": ("查询当前持仓列表", _tool_positions,
                      {"type": "object", "properties": {"direction": {"type": "string", "enum": ["", "BUY", "SELL"]}}}),
    "get_indicators": ("查询指定周期的最新指标值", _tool_indicators,
                       {"type": "object", "properties": {"timeframe": {"type": "string", "enum": ["M5", "M15", "M30", "H1", "H4", "D1"]}}}),
    "get_candles": ("查询最近 K 线", _tool_candles,
                    {"type": "object", "properties": {"timeframe": {"type": "string"}, "count": {"type": "integer"}}}),
    "get_account_info": ("查询账户余额/净值/保证金", _tool_account, {"type": "object"}),
    "get_trades_history": ("查询历史平仓成交", _tool_trades_history,
                           {"type": "object", "properties": {"limit": {"type": "integer"}}}),
    "get_market_price": ("查询当前买价/卖价/点差", _tool_market_price, {"type": "object"}),
    "get_gate_stats": ("查询近 24h 门禁拦截统计", _tool_gate_stats, {"type": "object"}),
    "get_shadow_summary": ("查询影子对照周报", _tool_shadow_summary, {"type": "object"}),
    "get_pa_analysis": ("触发 Price Action 两阶段分析（诊断+决策建议）", _tool_pa_analysis,
                        {"type": "object", "properties": {"timeframe": {"type": "string", "enum": ["M15", "M30", "H1"]}}}),
}


def openai_tools() -> list[dict]:
    return [{"type": "function", "function": {"name": n, "description": d, "parameters": p}}
            for n, (d, _, p) in TOOLS.items()]


def call_tool(name: str, args: dict) -> str:
    if name not in TOOLS:
        return f"未知工具 {name}"
    _, handler, _ = TOOLS[name]
    try:
        return str(handler(**(args or {})))
    except Exception as e:
        return f"工具错误: {e}"


# ── 会话持久化 ───────────────────────────────────────────────
def _chat_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(CHAT_DB)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE IF NOT EXISTS chat_sessions (id TEXT PRIMARY KEY, title TEXT,"
        " created_at TEXT, updated_at TEXT)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS chat_messages (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " session_id TEXT, role TEXT, content TEXT, created_at TEXT)")
    return conn


def _add_message(conn, session_id: str, role: str, content: str) -> int:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("INSERT INTO chat_messages (session_id, role, content, created_at)"
                 " VALUES (?,?,?,?)", (session_id, role, content, now))
    conn.execute("INSERT INTO chat_sessions (id, title, created_at, updated_at) VALUES (?,?,?,?)"
                 " ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at",
                 (session_id, content[:20], now, now))
    conn.commit()
    cur = conn.execute("SELECT MAX(id) FROM chat_messages WHERE session_id=?", (session_id,))
    return int(cur.fetchone()[0])


# ── Provider 最小层 ──────────────────────────────────────────
def _active_provider() -> dict | None:
    p = {
        "name": os.environ.get("LLM_NAME", "env"),
        "base_url": os.environ.get("LLM_BASE_URL", ""),
        "api_key": os.environ.get("LLM_API_KEY", ""),
        "model": os.environ.get("LLM_MODEL", ""),
        "type": os.environ.get("LLM_TYPE", "openai"),
    }
    if p["base_url"] and p["api_key"] and p["model"]:
        return p
    try:
        store = json.load(open(PROVIDERS_PATH, encoding="utf-8"))
        for prov in store.get("providers", []):
            if prov.get("is_active") and prov.get("api_key"):
                return prov
    except Exception:
        pass
    return None


@router.get("/llm/status")
def api_llm_status():
    p = _active_provider()
    return {"available": p is not None, "provider": (p or {}).get("name"),
            "model": (p or {}).get("model"), "base_url": (p or {}).get("base_url")}


@router.get("/llm/providers")
def api_llm_providers():
    try:
        return json.load(open(PROVIDERS_PATH, encoding="utf-8"))
    except Exception:
        return {"providers": []}


@router.post("/llm/providers")
def api_llm_save(provider: dict):
    os.makedirs(AI_DIR, exist_ok=True)
    store = {"providers": []}
    try:
        store = json.load(open(PROVIDERS_PATH, encoding="utf-8"))
    except Exception:
        pass
    provider["is_active"] = True
    store["providers"] = [q for q in store.get("providers", [])
                          if q.get("name") != provider.get("name")] + [provider]
    for q in store["providers"]:
        q["is_active"] = q is provider or q.get("name") == provider.get("name")
    json.dump(store, open(PROVIDERS_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return {"ok": True}


@router.get("/ai/agent-settings")
def api_agent_settings():
    try:
        return json.load(open(SETTINGS_PATH, encoding="utf-8"))
    except Exception:
        return {"tools_enabled": True, "memory_auto_accumulate": False}


class SettingsIn(BaseModel):
    tools_enabled: bool = True
    memory_auto_accumulate: bool = False


@router.put("/ai/agent-settings")
def api_agent_settings_put(body: SettingsIn):
    os.makedirs(AI_DIR, exist_ok=True)
    json.dump(body.model_dump(), open(SETTINGS_PATH, "w", encoding="utf-8"), indent=2)
    return {"ok": True}


@router.get("/ai/persona")
def api_persona_get():
    try:
        return {"soul": open(SOUL_PATH, encoding="utf-8").read()}
    except Exception:
        return {"soul": DEFAULT_SOUL}


class SoulIn(BaseModel):
    soul: str


@router.put("/ai/persona")
def api_persona_put(body: SoulIn):
    os.makedirs(AI_DIR, exist_ok=True)
    with open(SOUL_PATH, "w", encoding="utf-8") as f:
        f.write(body.soul[:2000])
    return {"ok": True}


# ── 会话 CRUD ────────────────────────────────────────────────
@router.get("/ai/sessions")
def api_sessions():
    conn = _chat_conn()
    try:
        rows = conn.execute(
            "SELECT s.id, s.title, s.updated_at, COUNT(m.id) FROM chat_sessions s"
            " LEFT JOIN chat_messages m ON m.session_id=s.id"
            " GROUP BY s.id ORDER BY s.updated_at DESC").fetchall()
    finally:
        conn.close()
    return [{"id": r[0], "title": r[1], "updated_at": r[2], "messages": r[3]} for r in rows]


@router.get("/ai/sessions/{sid}/messages")
def api_session_messages(sid: str):
    conn = _chat_conn()
    try:
        rows = conn.execute("SELECT role, content, created_at FROM chat_messages"
                            " WHERE session_id=? ORDER BY id", (sid,)).fetchall()
    finally:
        conn.close()
    return [{"role": r[0], "content": r[1], "created_at": r[2]} for r in rows]


class SessionIn(BaseModel):
    title: str = "新会话"


@router.post("/ai/sessions")
def api_session_create(body: SessionIn):
    sid = uuid.uuid4().hex[:8]
    conn = _chat_conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("INSERT INTO chat_sessions (id, title, created_at, updated_at) VALUES (?,?,?,?)",
                 (sid, body.title, now, now))
    conn.commit()
    conn.close()
    return {"id": sid}


@router.delete("/ai/sessions/{sid}")
def api_session_delete(sid: str):
    conn = _chat_conn()
    conn.execute("DELETE FROM chat_messages WHERE session_id=?", (sid,))
    conn.execute("DELETE FROM chat_sessions WHERE id=?", (sid,))
    conn.commit()
    conn.close()
    return {"ok": True}


@router.get("/ai/tools")
def api_ai_tools():
    return [{"name": n, "description": d} for n, (d, _, _) in TOOLS.items()]


# ── SSE 聊天（工具轮 ≤5，失败降级纯流式）────────────────────
class ChatIn(BaseModel):
    session_id: str
    message: str


def _chat_stream(body: ChatIn):
    import httpx
    prov = _active_provider()
    if prov is None:
        yield 'data: {"content": "未配置 LLM 提供商：设置环境变量 LLM_API_KEY/LLM_BASE_URL/LLM_MODEL，或在 /api/llm/providers 保存。", "done": true}\n\n'
        return
    conn = _chat_conn()
    _add_message(conn, body.session_id, "user", body.message)
    rows = conn.execute("SELECT role, content FROM chat_messages WHERE session_id=?"
                        " ORDER BY id DESC LIMIT 20", (body.session_id,)).fetchall()
    history = [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
    history = [m for m in history if not m["content"].startswith("⚠️")]
    conn.close()

    soul = DEFAULT_SOUL
    try:
        soul = open(SOUL_PATH, encoding="utf-8").read()
    except Exception:
        pass
    system = soul + TOOLING_RULES
    messages = [{"role": "system", "content": system}, *history]

    tools_on = api_agent_settings().get("tools_enabled", True)
    emitted = False
    try:
        with httpx.Client(timeout=90) as http:
            for round_no in range(5):
                payload = {"model": prov["model"], "messages": messages,
                           "stream": False, "temperature": 0.4}
                if tools_on:
                    payload["tools"] = openai_tools()
                r = http.post(prov["base_url"].rstrip("/") + "/chat/completions",
                              json=payload, headers={"Authorization": "Bearer " + prov["api_key"]})
                r.raise_for_status()
                msg = r.json()["choices"][0]["message"]
                tool_calls = msg.get("tool_calls") or []
                if tool_calls:
                    messages.append({"role": "assistant", "content": msg.get("content") or "",
                                     "tool_calls": tool_calls})
                    for tc in tool_calls:
                        name = tc["function"]["name"]
                        yield f'data: {json.dumps({"tool": f"调用 {name}…"}, ensure_ascii=False)}\n\n'
                        try:
                            args = json.loads(tc["function"].get("arguments") or "{}")
                        except json.JSONDecodeError:
                            args = {}
                        result = call_tool(name, args)
                        messages.append({"role": "tool", "tool_call_id": tc["id"],
                                         "content": result[:3000]})
                    continue
                content = msg.get("content") or ""
                for i in range(0, len(content), 20):
                    yield f'data: {json.dumps({"content": content[i:i+20]}, ensure_ascii=False)}\n\n'
                emitted = True
                break
            else:
                yield f'data: {json.dumps({"content": "（工具轮次达上限）"}, ensure_ascii=False)}\n\n'
        if not emitted:
            return
    except Exception as e:
        if emitted:
            yield f'data: {json.dumps({"content": f"\\n⚠️ {e}"}, ensure_ascii=False)}\n\n'
        else:
            yield f'data: {json.dumps({"content": f"⚠️ {e}", "error": True}, ensure_ascii=False)}\n\n'
    conn2 = _chat_conn()
    mid = _add_message(conn2, body.session_id, "assistant", "（见上）")
    conn2.close()
    yield f'data: {json.dumps({"done": True, "message_id": mid})}\n\n'


class ChatBody(BaseModel):
    session_id: str
    message: str


@router.post("/ai/chat")
def api_ai_chat(body: ChatBody):
    return StreamingResponse(_chat_stream(body), media_type="text/event-stream")

