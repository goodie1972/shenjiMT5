"""engine/reconcile.py — 对账（T1.6）：broker deals → trades 表真值。

契约依据：ARCHITECTURE §7 / PRD——MT5 的 history_deals_get 是全量成交流水，
对账按 position_id 聚合：缺失补录、pnl/exit_reason 以 broker 为准覆盖。
DEAL_REASON 映射：2=SL? 见 MQL5：DEAL_REASON_SL=4? 实际常量：
  DEAL_REASON_CLIENT=0, MOBILE=1, WEB=2, EXPERT=3, SL=4, TP=5, SO=6,...
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Optional

from config import settings
from data import database as db
from engine.journal import update_trade_reconciled

logger = logging.getLogger(__name__)

REASON_MAP = {4: "sl_triggered", 5: "tp_triggered"}
REASON_SL, REASON_TP = 4, 5
ENTRY_IN, ENTRY_OUT = 0, 1


def reconcile(client, lookback_days: int = 7,
              db_path: str = settings.DB_PATH) -> dict:
    """拉 deals 按 position_id 聚合，与 trades 表比对：
    - 引擎管理的平仓已写 trades 行 → 用 broker pnl/exit_price/exit_reason 覆盖；
    - broker 侧平仓（SL/TP/手动）无 trades 行 → 整条补录（exit_reason 取 deal reason）。
    """
    now = int(settings.utc_now())
    deals = client.deals_history(now - lookback_days * 86400, now + 86400)
    by_pos: dict[int, list[dict]] = defaultdict(list)
    for d in deals:
        if d["position_id"]:
            by_pos[int(d["position_id"])].append(d)

    stats = {"positions": len(by_pos), "updated": 0, "inserted": 0, "open": 0}
    conn = db.connect(db_path)
    try:
        known = {r[0] for r in conn.execute("SELECT position_ticket FROM trades")}
        for pos_id, ds in sorted(by_pos.items()):
            ins = [d for d in ds if d["entry"] == ENTRY_IN]
            outs = [d for d in ds if d["entry"] == ENTRY_OUT]
            if not ins:
                continue
            if not outs:
                stats["open"] += 1          # 在途仓位，不写 close 字段
                continue
            entry = sorted(ins, key=lambda d: d["time"])[0]
            exit_deal = sorted(outs, key=lambda d: d["time"])[-1]
            pnl = round(sum(d["profit"] + d["commission"] + d["swap"] for d in outs), 2)
            exit_reason = REASON_MAP.get(exit_deal["reason"], "mt5_history")
            volume = round(sum(d["volume"] for d in outs), 2)
            direction = "BUY" if entry["type"] == 0 else "SELL"
            strategy = _strategy_of(entry, conn)
            if pos_id in known:
                update_trade_reconciled(pos_id, pnl, float(exit_deal["price"]),
                                        exit_reason, close_ts=int(exit_deal["time"]),
                                        db_path=db_path)
                stats["updated"] += 1
            else:
                conn.execute(
                    "INSERT OR REPLACE INTO trades (position_ticket, strategy, magic,"
                    " direction, volume, entry_price, exit_price, sl, tp, pnl,"
                    " open_ts, close_ts, hold_seconds, exit_reason, mode)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (pos_id, strategy, int(entry["magic"]), direction, volume,
                     float(entry["price"]), float(exit_deal["price"]), None, None,
                     pnl, int(entry["time"]), int(exit_deal["time"]),
                     int(exit_deal["time"]) - int(entry["time"]), exit_reason,
                     "reconciled"))
                stats["inserted"] += 1
        conn.commit()
    finally:
        conn.close()
    if stats["updated"] or stats["inserted"]:
        logger.info("[reconcile] %s", stats)
    return stats


def _strategy_of(entry_deal: dict, conn) -> str:
    """策略名：优先开仓 deal comment（shenji:{name}），否则 magic 反查 signals。"""
    comment = entry_deal.get("comment") or ""
    if comment.startswith("shenji:") and len(comment) > 7:
        return comment[7:]
    row = conn.execute("SELECT strategy FROM signals WHERE magic=? AND status IN"
                       " ('opened','closed') ORDER BY id DESC LIMIT 1",
                       (int(entry_deal["magic"]),)).fetchone()
    return row[0] if row else f"magic:{entry_deal['magic']}"
