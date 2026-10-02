"""core/mt5_client.py — MetaTrader5 官方包的薄包装（唯一终端入口）。

语义决策落地点（docs/PRD.md）：
- D1 时区：终端返回的时间戳是 broker 服务器时间（秒）。本模块负责实测 server_offset
  并提供 to_utc()；入库前必须转换。偏移"实测不假设"，漂移 >30min 告警疑似 DST。
- D4/D5/D6：symbol spec（digits/point/filling/stops/账户模式）运行时取并缓存。
- D7：copy_rates 末根是 forming bar（bar0）；[-2] 才是 bar1——纪律在契约 INV-S1。

本文件禁止业务逻辑（门禁/策略/风控一律不进来）。
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Optional

from config import settings

logger = logging.getLogger(__name__)

# MT5 账户保证金模式（文档化常量，避免 import mt5 失败时不可用）
MARGIN_MODE_RETAIL_HEDGING = 2   # 对冲账户（同品种可双向/多单并存）
MARGIN_MODE_RETAIL_NETTING = 1   # 净持账户（同品种仓位合并）


def _load_mt5():
    """惰性加载 MetaTrader5 包，给出可操作的报错。"""
    try:
        import MetaTrader5 as mt5
    except ImportError as e:
        raise RuntimeError(
            "MetaTrader5 包未安装。前置条件：Windows + 64 位 Python；"
            "安装：pip install MetaTrader5"
        ) from e
    return mt5


class MT5Error(RuntimeError):
    """终端不可达 / 调用失败。"""


class MT5Client:
    """连接管理、symbol spec、行情读取、成交流水。M1 再加下单包装。"""

    def __init__(self, terminal_path: str = "", login: int = 0,
                 password: str = "", server: str = ""):
        self._mt5 = None
        self._initialized = False
        self._terminal_path = terminal_path
        self._login = login
        self._password = password
        self._server = server
        self._symbol_specs: dict[str, dict] = {}
        self.server_offset_sec: Optional[float] = None   # server_ts − utc_ts
        self._last_calibrated_at: float = 0.0
        self._load_persisted_offset()

    # ── 连接 ─────────────────────────────────────────────────
    def connect(self) -> dict:
        """初始化终端连接。已在运行的终端直接挂载；否则按需指定路径/账号。"""
        mt5 = _load_mt5()
        self._mt5 = mt5
        kwargs: dict[str, Any] = {}
        if self._terminal_path:
            kwargs["path"] = self._terminal_path
        if self._login:
            kwargs.update(login=self._login, password=self._password,
                          server=self._server)
        if not mt5.initialize(**kwargs):
            raise MT5Error(f"MT5 initialize 失败: {mt5.last_error()}（检查：终端已启动？"
                           "允许算法交易已勾选？64 位 Python？）")
        self._initialized = True
        self.calibrate_offset()
        info = self.account_summary()
        logger.info("[MT5] connected: login=%s server=%s", info.get("login"), info.get("server"))
        return info

    def ensure_connected(self) -> None:
        if not self._initialized:
            self.connect()
        elif not self._mt5.terminal_info():
            self._initialized = False
            self.connect()

    def shutdown(self) -> None:
        if self._initialized and self._mt5 is not None:
            self._mt5.shutdown()
            self._initialized = False

    # ── 账户（D5 探测点）──────────────────────────────────────
    def account_summary(self) -> dict:
        mt5 = self._mt5
        acc = mt5.account_info()
        if acc is None:
            raise MT5Error(f"account_info 失败: {mt5.last_error()}")
        margin_mode = int(acc.margin_mode)
        return {
            "login": acc.login,
            "server": acc.server,
            "currency": acc.currency,
            "balance": acc.balance,
            "equity": acc.equity,
            "trade_allowed": bool(acc.trade_allowed),
            "margin_mode": margin_mode,
            "margin_mode_name": {
                MARGIN_MODE_RETAIL_HEDGING: "hedging（对冲）",
                MARGIN_MODE_RETAIL_NETTING: "netting（净持）",
            }.get(margin_mode, f"unknown({margin_mode})"),
        }

    # ── symbol spec（D4/D6 探测点）───────────────────────────
    def symbol_spec(self, symbol: str) -> dict:
        """读取并缓存 symbol 规约。digits/point/filling/stops 一律以此为准，禁止硬编码。"""
        if symbol in self._symbol_specs:
            return self._symbol_specs[symbol]
        mt5 = self._mt5
        if not mt5.symbol_select(symbol, True):
            raise MT5Error(f"symbol_select({symbol}) 失败: {mt5.last_error()}")
        si = mt5.symbol_info(symbol)
        if si is None:
            raise MT5Error(f"symbol_info({symbol}) 失败: {mt5.last_error()}")
        spec = {
            "symbol": symbol,
            "digits": si.digits,
            "point": si.point,
            "volume_min": si.volume_min,
            "volume_step": si.volume_step,
            "volume_max": si.volume_max,
            "trade_tick_value": si.trade_tick_value,
            "trade_tick_size": si.trade_tick_size,
            "stops_level": si.trade_stops_level,
            "freeze_level": si.trade_freeze_level,
            "filling_mode_mask": int(si.filling_mode),
            "trade_mode": int(si.trade_mode),
            # 便捷推导：XAUUSD 常见 1 pip = 10*point（3 位）或 1*point（2 位）——
            # 以 pip_size 统一表述，策略代码不得再硬编码 0.01
            "pip_size": si.point * (10 if si.digits >= 3 else 1),
        }
        self._symbol_specs[symbol] = spec
        return spec

    # ── 行情 ─────────────────────────────────────────────────
    def get_tick(self, symbol: str) -> dict:
        self.ensure_connected()
        t = self._mt5.symbol_info_tick(symbol)
        if t is None:
            raise MT5Error(f"symbol_info_tick({symbol}) 失败: {self._mt5.last_error()}")
        return {"time": t.time, "bid": t.bid, "ask": t.ask,
                "last": t.last, "volume": t.volume}

    def copy_rates(self, symbol: str, timeframe: str, count: int) -> list[dict]:
        """拉 K 线，升序返回；**末根是 forming bar（bar0）**，bar1 = [-2]（INV-S1）。

        返回 dict 键：time(server 秒)/open/high/low/close/tick_volume。
        入库前必须经 to_utc() 转换（contract_data §2）。
        """
        self.ensure_connected()
        mt5 = self._mt5
        tf = getattr(mt5, f"TIMEFRAME_{timeframe}", None)
        if tf is None:
            raise MT5Error(f"未知周期: {timeframe}")
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
        if rates is None:
            raise MT5Error(f"copy_rates_from_pos({symbol},{timeframe}) 失败: {mt5.last_error()}")
        return [
            {"time": int(r["time"]), "open": float(r["open"]), "high": float(r["high"]),
             "low": float(r["low"]), "close": float(r["close"]), "volume": int(r["tick_volume"])}
            for r in rates
        ]

    def copy_ticks(self, symbol: str, from_ts_utc: float, to_ts_utc: float) -> list[dict]:
        """拉 real ticks（UTC 秒入参）。M2 real-tick 验证层用。"""
        self.ensure_connected()
        mt5 = self._mt5
        ticks = mt5.copy_ticks_range(symbol, int(from_ts_utc), int(to_ts_utc), mt5.COPY_TICKS_ALL)
        if ticks is None:
            raise MT5Error(f"copy_ticks_range 失败: {mt5.last_error()}")
        return [{"time": int(t["time"]), "bid": float(t["bid"]), "ask": float(t["ask"])}
                for t in ticks]

    # ── 成交流水（对账）───────────────────────────────────────
    def deals_history(self, from_ts_utc: float, to_ts_utc: float) -> list[dict]:
        """拉区间内全部 deals；对账按 position_id 聚合（contract_strategy §7.1）。"""
        self.ensure_connected()
        mt5 = self._mt5
        deals = mt5.history_deals_get(int(from_ts_utc), int(to_ts_utc))
        if deals is None:
            raise MT5Error(f"history_deals_get 失败: {mt5.last_error()}")
        return [{
            "ticket": d.ticket, "position_id": d.position_id, "order": d.order,
            "type": int(d.type), "entry": int(d.entry), "volume": d.volume,
            "price": d.price, "profit": d.profit, "commission": d.commission,
            "swap": d.swap, "magic": d.magic, "comment": d.comment,
            "time": int(d.time),
        } for d in deals]

    # ── 时区（D1）────────────────────────────────────────────
    def calibrate_offset(self) -> float:
        """实测 server offset = 最新 tick.time − 本机 UTC。每 6h 重校；漂移>30min 告警疑似 DST。"""
        self.ensure_connected()
        tick = self.get_tick(settings.SYMBOL)
        server_ts = tick["time"]
        now_utc = time.time()
        new_offset = float(server_ts - now_utc)
        # tick.time 是秒级，取整误差容忍 60s
        if self.server_offset_sec is None or abs(new_offset - self.server_offset_sec) > 60:
            if self.server_offset_sec is not None:
                drift = abs(new_offset - self.server_offset_sec)
                if drift > 1800:
                    logger.warning("[TimeSync] ⚠️ 服务器偏移漂移 %.2fh（旧 %.2fh → 新 %.2fh），"
                                   "疑似 broker DST 切换，已更新", drift / 3600.0,
                                   self.server_offset_sec / 3600.0, new_offset / 3600.0)
            self.server_offset_sec = new_offset
            self._persist_offset()
        self._last_calibrated_at = now_utc
        return self.server_offset_sec

    def maybe_recalibrate(self, interval_sec: float = 6 * 3600) -> None:
        if time.time() - self._last_calibrated_at >= interval_sec:
            self.calibrate_offset()

    def to_utc(self, server_ts: int) -> int:
        """server 时间戳 → UTC 秒（入库前唯一通道）。offset 未校准时报错（fail-closed）。"""
        if self.server_offset_sec is None:
            raise MT5Error("server_offset 未校准，拒绝转换时间戳（禁止把 server time 写入库）")
        return int(server_ts - self.server_offset_sec)

    def _persist_offset(self) -> None:
        try:
            os.makedirs(settings.DATA_DIR, exist_ok=True)
            with open(settings.SERVER_OFFSET_PATH, "w", encoding="utf-8") as f:
                json.dump({"server_offset_sec": self.server_offset_sec,
                           "calibrated_at": time.time()}, f)
        except OSError as e:
            logger.warning("[TimeSync] offset 持久化失败: %s", e)

    def _load_persisted_offset(self) -> None:
        try:
            with open(settings.SERVER_OFFSET_PATH, encoding="utf-8") as f:
                data = json.load(f)
            self.server_offset_sec = data.get("server_offset_sec")
        except (OSError, ValueError, json.JSONDecodeError):
            self.server_offset_sec = None
