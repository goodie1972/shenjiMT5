"""engine/reconcile 单测 — deals 按 position_id 聚合：覆盖 + 补录。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from data import database as db
from engine import reconcile


class FakeDealsClient:
    def __init__(self, deals):
        self._deals = deals

    def deals_history(self, from_ts, to_ts):
        return self._deals


T0 = 1_800_000_000


def deal(pos, entry, price, profit, reason=0, vol=0.01, magic=661901,
         kind=0, comment="shenji:smoke", t=T0):
    return {"ticket": pos * 10 + entry, "position_id": pos, "order": pos,
            "type": kind, "entry": entry, "volume": vol, "price": price,
            "profit": profit, "commission": -0.02, "swap": 0.0,
            "magic": magic, "comment": comment, "reason": reason, "time": t}


@pytest.fixture()
def tmp_db(tmp_path):
    path = str(tmp_path / "r.db")
    db.init_db(path)
    return path


class TestReconcile:
    def test_updates_engine_managed_close(self, tmp_db):
        """引擎已写 trades 行（pnl=本地估计）→ broker 真值覆盖。"""
        conn = db.connect(tmp_db)
        conn.execute("INSERT INTO trades (position_ticket, strategy, magic, direction,"
                     " volume, entry_price, open_ts, mode) VALUES"
                     " (9001, 'smoke', 661901, 'BUY', 0.01, 1997.1, ?, 'demo')", (T0,))
        conn.commit()
        conn.close()
        client = FakeDealsClient([
            deal(9001, reconcile.ENTRY_IN, 1997.1, 0.0, kind=0),
            deal(9001, reconcile.ENTRY_OUT, 1999.5, 2.40, reason=reconcile.REASON_SL,
                 kind=1, t=T0 + 3600),
        ])
        stats = reconcile.reconcile(client, db_path=tmp_db)
        assert stats["updated"] == 1
        ro = db.readonly_connect(tmp_db)
        r = ro.execute("SELECT pnl, pnl_source, exit_price, exit_reason, close_ts,"
                       " hold_seconds FROM trades WHERE position_ticket=9001").fetchone()
        ro.close()
        assert r["pnl"] == pytest.approx(2.40 - 0.02)      # profit + commission
        assert r["pnl_source"] == "broker"
        assert r["exit_price"] == 1999.5
        assert r["exit_reason"] == "sl_triggered"          # DEAL_REASON_SL=4
        assert r["hold_seconds"] == 3600

    def test_inserts_broker_closed_position(self, tmp_db):
        """broker 侧平仓（如手动）无 trades 行 → 整条补录，策略名取 comment。"""
        client = FakeDealsClient([
            deal(9002, reconcile.ENTRY_IN, 1997.1, 0.0, kind=0),
            deal(9002, reconcile.ENTRY_OUT, 1996.0, -1.1, kind=1, t=T0 + 600),
        ])
        stats = reconcile.reconcile(client, db_path=tmp_db)
        assert stats["inserted"] == 1
        ro = db.readonly_connect(tmp_db)
        r = ro.execute("SELECT strategy, direction, pnl, exit_reason FROM trades"
                       " WHERE position_ticket=9002").fetchone()
        ro.close()
        assert r["strategy"] == "smoke"
        assert r["direction"] == "BUY"
        assert r["pnl"] == pytest.approx(-1.12)
        assert r["exit_reason"] == "mt5_history"

    def test_open_positions_skipped(self, tmp_db):
        client = FakeDealsClient([
            deal(9003, reconcile.ENTRY_IN, 1997.1, 0.0, kind=0),
        ])
        stats = reconcile.reconcile(client, db_path=tmp_db)
        assert stats["open"] == 1 and stats["inserted"] == 0
        ro = db.readonly_connect(tmp_db)
        assert ro.execute("SELECT COUNT(*) FROM trades").fetchone()[0] == 0
