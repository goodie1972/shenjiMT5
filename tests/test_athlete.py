"""engine/athlete 单测 — G15 复核窗口、去重、ATR 兜底 SL/TP、fail-closed。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from config import settings
from data import database as db
from engine.athlete import Athlete
from engine.journal import TradeJournal


class FakeClient:
    def __init__(self, bid=1996.0, ask=1996.1):
        self.bid, self.ask = bid, ask
        self.orders = []

    def get_tick(self, symbol):
        return {"bid": self.bid, "ask": self.ask, "time": 1, "last": 0.0, "volume": 0}

    def symbol_spec(self, symbol):
        return {"volume_step": 0.01, "volume_min": 0.01, "trade_tick_size": 0.01,
                "trade_tick_value": 0.1, "filling_mode_mask": 3}

    def order_send(self, symbol, direction, volume, sl=None, tp=None,
                   magic=0, comment="", deviation=30):
        self.orders.append({"direction": direction, "volume": volume,
                            "sl": sl, "tp": tp, "magic": magic, "comment": comment})
        return {"order_ticket": 9001, "deal_ticket": 1, "price": self.ask,
                "volume": volume, "retcode": 10009, "filling": "FOK"}


class FakeStrategy:
    name = "fake"
    magic = 661901
    timeframe = "M5"
    verify_ok = True
    atr = 4.0

    def _verify_entry(self, signal, price, latest):
        return self.verify_ok

    def get_dynamic_sl_tp(self, direction, price):
        return None, None

    def get_indicator(self, name):
        return self.atr

    def mark_extreme_entry(self, ticket):
        self.marked = ticket


def make_athlete(tmp_db):
    return Athlete(FakeClient(), TradeJournal(), db_path=tmp_db)


def submit_with_signal(a, s, direction="BUY", db_path=None):
    """模拟引擎流程：先插 signals 行，再提交 ticket。返回 signal_id。"""
    sid = db.insert_signal(s.name, s.magic, s.timeframe, direction, db_path=db_path)
    assert a.submit(s, sid, direction, {}) is not None
    return sid


@pytest.fixture()
def tmp_db(tmp_path):
    path = str(tmp_path / "a.db")
    db.init_db(path)
    return path


class TestSubmitDedupe:
    def test_same_magic_direction_rejected(self, tmp_db):
        a = make_athlete(tmp_db)
        s = FakeStrategy()
        assert a.submit(s, 1, "BUY", {}) is not None
        assert a.submit(s, 2, "BUY", {}) is None        # 在途 ticket
        a.open_entries[9001] = type("E", (), {"magic": 661901, "direction": "SELL"})()
        assert a.submit(s, 3, "SELL", {}) is None       # 已持同向仓
        assert a.submit(s, 4, "BUY", {}) is None


class TestVerifyTick:
    def test_pass_first_tick_opens_with_atr_fallback(self, tmp_db, monkeypatch):
        monkeypatch.setattr(settings, "utc_now", lambda: 1_800_000_000)
        a = make_athlete(tmp_db)
        s = FakeStrategy()
        submit_with_signal(a, s, db_path=tmp_db)
        executed = a.verify_tick({"M5": {"candles": [], "indicators": {"atr": 4.0}}})
        assert len(executed) == 1
        order = a.client.orders[0]
        assert order["sl"] == pytest.approx(1996.1 - 2 * 4.0, abs=0.01)   # 2×ATR
        assert order["tp"] == pytest.approx(1996.1 + 4 * 4.0, abs=0.01)   # 4×ATR
        assert a.open_entries[9001].direction == "BUY"
        ro = db.readonly_connect(tmp_db)
        sig = ro.execute("SELECT status, position_ticket FROM signals").fetchone()
        trade = ro.execute("SELECT open_ts FROM trades").fetchone()
        ro.close()
        assert sig["status"] == "opened" and sig["position_ticket"] == 9001
        assert trade["open_ts"] == 1_800_000_000

    def test_expired_after_three_failed_verifications(self, tmp_db):
        a = make_athlete(tmp_db)
        s = FakeStrategy()
        s.verify_ok = False
        submit_with_signal(a, s, db_path=tmp_db)
        a.verify_tick({})
        a.verify_tick({})
        assert len(a.pending) == 1                 # 前两 tick 保留
        a.verify_tick({})
        assert not a.pending and not a.client.orders
        ro = db.readonly_connect(tmp_db)
        sig = ro.execute("SELECT status, exit_reason FROM signals").fetchone()
        ro.close()
        assert sig["status"] == "voided" and sig["exit_reason"] == "G15:tick_expired"

    def test_no_tick_never_orders(self, tmp_db):
        a = make_athlete(tmp_db)
        a.client.bid = a.client.ask = 0.0            # 行情缺失
        s = FakeStrategy()
        submit_with_signal(a, s, db_path=tmp_db)
        for _ in range(3):
            a.verify_tick({})
        assert not a.client.orders and not a.pending

    def test_verify_exception_fail_closed(self, tmp_db):
        a = make_athlete(tmp_db)
        s = FakeStrategy()
        s._verify_entry = lambda *a2, **k: 1 / 0     # 复核钩子抛异常
        submit_with_signal(a, s, db_path=tmp_db)
        for _ in range(3):
            a.verify_tick({})
        assert not a.client.orders and not a.pending
        ro = db.readonly_connect(tmp_db)
        assert ro.execute("SELECT status FROM signals").fetchone()[0] == "voided"


class TestOrderFailure:
    def test_order_send_error_voids_signal(self, tmp_db, monkeypatch):
        a = make_athlete(tmp_db)
        from core.mt5_client import MT5Error
        a.client.order_send = lambda *a2, **k: (_ for _ in ()).throw(MT5Error("拒单"))
        s = FakeStrategy()
        submit_with_signal(a, s, db_path=tmp_db)
        executed = a.verify_tick({})
        assert not executed and not a.pending
        ro = db.readonly_connect(tmp_db)
        sig = ro.execute("SELECT status, exit_reason FROM signals").fetchone()
        ro.close()
        assert sig["status"] == "voided" and sig["exit_reason"] == "order_failed"
