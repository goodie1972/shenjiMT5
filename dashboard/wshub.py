"""dashboard/wshub.py — 最小 WS hub（U-E1：prices/positions/account 三通道 + logs）。

协议（与旧库一致）：/ws 端点，服务端推 JSON {channel, data}。
节奏：prices 1s（tick）→ positions/account 5s → logs 5s。
客户端断开自动清理；零客户端时跳过采集。
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

from fastapi import WebSocket

from config import settings

logger = logging.getLogger(__name__)

_connections: set[WebSocket] = set()
_broadcaster_started = False


async def register(ws: WebSocket) -> None:
    await ws.accept()
    _connections.add(ws)


def unregister(ws: WebSocket) -> None:
    _connections.discard(ws)


async def broadcast(channel: str, data) -> None:
    if not _connections:
        return
    dead = []
    payload = {"channel": channel, "data": data}
    for ws in list(_connections):
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _connections.discard(ws)


def _read_logs_since(offset_path: str):
    path = os.path.join(settings.LOG_DIR, "engine.log")
    if not os.path.exists(path):
        return []
    try:
        with open(offset_path, encoding="utf-8") as f:
            pos = int(f.read().strip() or 0)
    except (OSError, ValueError):
        pos = 0
    size = os.path.getsize(path)
    if pos > size:
        pos = 0                                    # 日志轮转
    if size == pos:
        return [], pos
    with open(path, encoding="utf-8", errors="ignore") as f:
        f.seek(pos)
        new = f.read()
        new_pos = f.tell()
    with open(offset_path, "w", encoding="utf-8") as f:
        f.write(str(new_pos))
    out = []
    for ln in new.splitlines():
        parts = ln.split(" ", 3)
        if len(parts) >= 4:
            out.append({"timestamp": parts[0], "level": parts[1],
                        "name": parts[2], "message": parts[3]})
    return out, new_pos


async def broadcaster() -> None:
    """每秒一轮：tick → prices；每 5 轮：positions/account/logs。"""
    global _broadcaster_started
    if _broadcaster_started:
        return
    _broadcaster_started = True

    from core.mt5_client import MT5Client
    client_ref: list = [None]

    def get_c():
        if client_ref[0] is None:
            try:
                c = MT5Client()
                c.connect()
                client_ref[0] = c
            except Exception:
                client_ref[0] = None
        return client_ref[0]

    logs_pos_path = os.path.join(settings.LOG_DIR, "ws_logs.pos")
    tick_count = 0
    while True:
        try:
            if not _connections:
                await asyncio.sleep(1)
                continue
            c = get_c()
            if c is not None:
                try:
                    t = c.get_tick(settings.SYMBOL)
                    await broadcast("prices", {"bid": t["bid"], "ask": t["ask"],
                                               "spread": round(t["ask"] - t["bid"], 2)})
                except Exception:
                    pass
                if tick_count % 5 == 0:
                    try:
                        await broadcast("positions", c.positions_open(settings.SYMBOL))
                    except Exception:
                        pass
                    try:
                        await broadcast("account", c.account_summary())
                    except Exception:
                        pass
            if tick_count % 5 == 0:
                try:
                    logs, _ = _read_logs_since(logs_pos_path)
                    for entry in logs[-50:]:
                        await broadcast("logs", entry)
                except Exception:
                    pass
        except Exception:
            logger.exception("[wshub] 广播轮异常")
        tick_count += 1
        await asyncio.sleep(1)
