"""engine/journal.py — 交易日志（T1.5）：append-only jsonl + trades 表。

纪律（AGENTS §1.5 动钱日志）：每笔平仓必须落一行，字段全 UTC 秒。
jsonl 是追加型原始记录（engine 管理的平仓当场写）；trades 表是可被对账
（reconcile）修正的权威视图（pnl 以 broker 成交流水为准）。
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from config import settings
from data import database as db

logger = logging.getLogger(__name__)

FIELDS = ["position_ticket", "strategy", "magic", "direction", "volume",
          "entry_price", "exit_price", "sl", "tp", "pnl", "pnl_source",
          "open_ts", "close_ts", "hold_seconds", "exit_reason", "mode", "source"]


class TradeJournal:
    def __init__(self, journal_dir: Optional[str] = None):
        # 注意：默认参数在 import 时求值，测试要换目录必须传 None 再读 settings
        self.dir = journal_dir or settings.JOURNAL_DIR
        os.makedirs(self.dir, exist_ok=True)
        self.path = os.path.join(self.dir, "closed_trades.jsonl")

    def append(self, record: dict, db_path: str = settings.DB_PATH) -> None:
        line = {k: record.get(k) for k in FIELDS if k in record}
        line.setdefault("close_ts", int(settings.utc_now()))
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")
        self._upsert_trade(line, db_path=db_path)

    def _upsert_trade(self, line: dict, db_path: str) -> None:
        """同步 trades 表（对账可覆盖 pnl/exit_reason）。"""
        hold = None
        if line.get("open_ts") and line.get("close_ts"):
            hold = int(line["close_ts"] - line["open_ts"])
        conn = db.connect(db_path)
        try:
            conn.execute(
                "INSERT OR REPLACE INTO trades (position_ticket, strategy, magic,"
                " direction, volume, entry_price, exit_price, sl, tp, pnl,"
                " open_ts, close_ts, hold_seconds, exit_reason, mode)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (line.get("position_ticket"), line.get("strategy"),
                 line.get("magic"), line.get("direction"), line.get("volume"),
                 line.get("entry_price"), line.get("exit_price"), line.get("sl"),
                 line.get("tp"), line.get("pnl"), line.get("open_ts"),
                 line.get("close_ts"), hold, line.get("exit_reason"),
                 line.get("mode")))
            conn.commit()
        finally:
            conn.close()


def update_trade_reconciled(position_ticket: int, pnl: float, exit_price: float,
                            exit_reason: Optional[str], close_ts: Optional[int] = None,
                            db_path: str = settings.DB_PATH) -> None:
    """对账修正：以 broker 成交流水覆盖 pnl/exit_price/exit_reason，并补 close_ts。"""
    conn = db.connect(db_path)
    try:
        conn.execute(
            "UPDATE trades SET pnl=?, exit_price=COALESCE(?, exit_price),"
            " exit_reason=COALESCE(?, exit_reason), pnl_source='broker',"
            " close_ts=COALESCE(close_ts, ?),"
            " hold_seconds=COALESCE(hold_seconds, ? - open_ts)"
            " WHERE position_ticket=?",
            (pnl, exit_price, exit_reason, close_ts, close_ts, int(position_ticket)))
        conn.commit()
    finally:
        conn.close()
