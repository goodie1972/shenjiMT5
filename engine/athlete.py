"""engine/athlete.py — 运动员（轨道3，T1.3）：ticket 复核 → 下单 → 持仓登记。

契约：G15 = 3-tick 复核（超时/复核失败 → void，不入场不告警）；
下单 filling 自适应（core.mt5_client.select_filling）；SL/TP 缺省时用
cache 的 ATR 兜底 2×/4×（settings.FALLBACK_*_ATR_MULT）。
复核输入只有 bar1 缓存 + 实时 tick 价格（INV-S1：forming bar 仅价格触发）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from config import settings
from data import database as db

logger = logging.getLogger(__name__)


@dataclass
class Ticket:
    signal_id: int
    strategy_name: str
    magic: int
    timeframe: str
    direction: str                      # BUY/SELL
    strategy: object                    # 策略实例（_verify_entry/SL/TP 钩子）
    ticks_left: int = settings.ATHLETE_MAX_TICKS
    volume: float = settings.LOT_SIZE


@dataclass
class OpenEntry:
    """引擎在管的在途持仓（出场判定 + journal 的锚点）。"""
    position_ticket: int
    strategy_name: str
    magic: int
    timeframe: str
    direction: str
    volume: float
    entry_price: float
    open_ts: int
    sl: Optional[float] = None
    tp: Optional[float] = None
    strategy: object = field(default=None, repr=False)
    mode: str = "demo"


class Athlete:
    def __init__(self, client, journal, db_path: str = settings.DB_PATH,
                 symbol: str = settings.SYMBOL, mode: str = "demo"):
        self.client = client
        self.journal = journal
        self.db_path = db_path
        self.symbol = symbol
        self.mode = mode
        self.pending: list[Ticket] = []
        self.open_entries: dict[int, OpenEntry] = {}

    # ── 提交（引擎门禁放行后调用）────────────────────────────
    def submit(self, strategy, signal_id: int, direction: str,
               sig: dict) -> Optional[Ticket]:
        """同策略同方向去重（在途 ticket 或已持同向仓 → 拒收）。"""
        if any(t.magic == strategy.magic and t.direction == direction
               for t in self.pending):
            logger.info("[athlete] %s %s 在途 ticket 存在，拒收", strategy.name, direction)
            return None
        if any(e.magic == strategy.magic and e.direction == direction
               for e in self.open_entries.values()):
            logger.info("[athlete] %s %s 已持同向仓，拒收", strategy.name, direction)
            return None
        ticket = Ticket(signal_id=signal_id, strategy_name=strategy.name,
                        magic=strategy.magic, timeframe=strategy.timeframe,
                        direction=direction, strategy=strategy)
        self.pending.append(ticket)
        return ticket

    # ── 每 tick：复核 → 执行 ─────────────────────────────────
    def verify_tick(self, caches: dict[str, dict]) -> list[dict]:
        """G15：每个 pending ticket 消耗一 tick；复核通过即市价入场。

        tick 耗尽（3 次复核未过）→ void；无行情视同复核失败（绝不盲下）。
        """
        executed: list[dict] = []
        for ticket in list(self.pending):
            ticket.ticks_left -= 1
            cache = caches.get(ticket.timeframe) or {}
            latest = cache.get("indicators", {})
            tick = self._safe_tick()
            price = tick["ask"] if ticket.direction == "BUY" else tick["bid"]
            if tick["bid"] <= 0 or tick["ask"] <= 0:
                ok = False
            else:
                try:
                    # 契约形状 = {"direction": ...}（base.py §_verify_entry /
                    # test_followave 同款）。曾误传 {"signal": ...}——策略读不到
                    # direction 默认 "BUY"，所有 SELL 信号被 BUY 规则复核而作废。
                    # latest = 完整缓存（candles + indicators）——策略复核钩子可能需要
                    # forming bar 实体方向（INV-S1.2 白名单内的价格/实体触发）
                    ok = ticket.strategy._verify_entry(
                        {"direction": ticket.direction},
                        price, cache)
                except Exception:
                    logger.exception("[athlete] _verify_entry 异常（fail-closed）")
                    ok = False
            if not ok:
                if ticket.ticks_left <= 0:
                    self._void(ticket, "G15:tick_expired")
                continue
            self.pending.remove(ticket)
            opened = self._execute(ticket, price)
            if opened:
                executed.append(opened)
        return executed

    def _void(self, ticket: Ticket, reason: str) -> None:
        if ticket in self.pending:
            self.pending.remove(ticket)
        db.update_signal_status(ticket.signal_id, "voided", exit_reason=reason,
                                db_path=self.db_path)
        logger.info("[athlete] #%d voided: %s", ticket.signal_id, reason)

    def _safe_tick(self) -> dict:
        try:
            return self.client.get_tick(self.symbol)
        except Exception:
            logger.exception("[athlete] tick 获取失败（fail-closed：本 tick 不入场）")
            return {"bid": 0.0, "ask": 0.0}

    # ── 下单 ─────────────────────────────────────────────────
    def _execute(self, ticket: Ticket, price: float) -> Optional[dict]:
        sl, tp = ticket.strategy.get_dynamic_sl_tp(ticket.direction, price)
        if sl is None and tp is None:
            atr = self._strategy_atr(ticket)
            if atr and atr > 0:
                sign = 1.0 if ticket.direction == "BUY" else -1.0
                sl = round(price - sign * settings.FALLBACK_SL_ATR_MULT * atr, 2)
                tp = round(price + sign * settings.FALLBACK_TP_ATR_MULT * atr, 2)
        try:
            result = self.client.order_send(
                self.symbol, ticket.direction, ticket.volume,
                sl=sl, tp=tp, magic=ticket.magic,
                comment=f"shenji:{ticket.strategy_name}")
        except Exception:
            logger.exception("[athlete] #%d 下单失败", ticket.signal_id)
            db.update_signal_status(ticket.signal_id, "voided",
                                    exit_reason="order_failed", db_path=self.db_path)
            return None
        if price <= 0:
            logger.error("[athlete] tick 异常价格 0，放弃登记（单已发出，靠对账兜底）")
            return None
        position_ticket = result["order_ticket"]   # 对冲账户 position_id = 开仓单票
        db.update_signal_status(ticket.signal_id, "opened",
                                position_ticket=position_ticket,
                                db_path=self.db_path)
        entry = OpenEntry(position_ticket=position_ticket,
                          strategy_name=ticket.strategy_name, magic=ticket.magic,
                          timeframe=ticket.timeframe, direction=ticket.direction,
                          volume=result["volume"], entry_price=result["price"],
                          open_ts=int(settings.utc_now()), sl=sl, tp=tp,
                          strategy=ticket.strategy, mode=self.mode)
        self.open_entries[position_ticket] = entry
        ticket.strategy.mark_extreme_entry(position_ticket)
        logger.info("[athlete] #%d OPEN %s %.2f @ %.2f sl=%s tp=%s ticket=%s",
                    ticket.signal_id, ticket.direction, entry.volume,
                    entry.entry_price, sl, tp, position_ticket)
        self._insert_trade_row(entry)
        return {"ticket": entry, "result": result}

    def _strategy_atr(self, ticket: Ticket) -> Optional[float]:
        try:
            return ticket.strategy.get_indicator("atr")
        except Exception:
            return None

    def _insert_trade_row(self, e: OpenEntry) -> None:
        """开仓即写 trades 行（pnl 空）；平仓更新；对账以 broker 流水覆盖。"""
        conn = db.connect(self.db_path)
        try:
            conn.execute(
                "INSERT OR REPLACE INTO trades (position_ticket, strategy, magic,"
                " direction, volume, entry_price, sl, tp, open_ts, mode)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (e.position_ticket, e.strategy_name, e.magic, e.direction,
                 e.volume, e.entry_price, e.sl, e.tp, e.open_ts, e.mode))
            conn.commit()
        finally:
            conn.close()
