"""engine/engine 集成测试 — 冒烟策略跑通 取数→指标→打分→门禁→入库 管道。"""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from config import settings
from data import database as db
from engine.engine import Engine

SERVER_OFFSET = 10800
FIXED_NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc).timestamp()  # 周五午间


class FakeEngineClient:
    """引擎所需的最小 fake：行情 + 账户 + 持仓 + 下单/平仓 + spec。"""

    def __init__(self, n_bars=30):
        bars = []
        closes = [2010.0 - i * 0.5 for i in range(28)]     # 27 根连续下跌
        closes += [1997.1]                                  # bar1：小幅收阳
        for i, c in enumerate(closes):
            o = c - 0.5 if i < 28 else 1996.5               # 末根开=前收，收高于开
            if i == 28:
                o = 1996.5
            bars.append({"time": int(FIXED_NOW + SERVER_OFFSET - (n_bars - 1 - i) * 300),
                         "open": o, "high": max(o, c) + 0.4,
                         "low": min(o, c) - 0.4, "close": c, "volume": 100 + i})
        bars.append({"time": int(FIXED_NOW + SERVER_OFFSET),        # forming bar
                     "open": 1997.1, "high": 1997.5, "low": 1996.8,
                     "close": 1996.9, "volume": 99})
        self.bars = bars
        self.server_offset_sec = float(SERVER_OFFSET)
        self.orders = []
        self.closes = []
        self.exit_hook = False       # True → 策略 check_ema20_exit 立即平仓

    # client 接口
    def connect(self):
        return None

    def shutdown(self):
        return None

    def maybe_recalibrate(self):
        return None

    def account_summary(self):
        return {"login": 1, "server": "Fake", "balance": 10_000.0,
                "margin_mode": 2, "margin_mode_name": "hedging（对冲）"}

    def positions_open(self, symbol):
        if not self.orders:
            return []
        return [{"ticket": o["order_ticket"], "magic": o["magic"], "type": "BUY",
                 "volume": o["volume"], "price_open": o["price"],
                 "profit": 1.5, "time": int(FIXED_NOW)} for o in self.orders]

    def get_tick(self, symbol):
        return {"bid": 1996.0, "ask": 1996.1, "time": int(FIXED_NOW),
                "last": 0.0, "volume": 0}

    def symbol_spec(self, symbol):
        return {"symbol": symbol, "digits": 2, "point": 0.01, "pip_size": 0.01,
                "volume_min": 0.01, "volume_step": 0.01, "volume_max": 100.0,
                "trade_tick_value": 0.1, "trade_tick_size": 0.01,
                "stops_level": 0, "freeze_level": 0, "filling_mode_mask": 3,
                "trade_mode": 4}

    def order_send(self, symbol, direction, volume, sl=None, tp=None,
                   magic=0, comment="", deviation=30):
        req = {"symbol": symbol, "direction": direction, "volume": volume,
               "sl": sl, "tp": tp, "magic": magic, "comment": comment}
        result = {"order_ticket": 9001 + len(self.orders), "deal_ticket": 8001,
                  "price": 1997.1, "volume": volume, "retcode": 10009,
                  "filling": "FOK"}
        self.orders.append({**req, **result})
        return result

    def close_position(self, symbol, position_ticket, direction, volume,
                       magic=0, deviation=30):
        result = {"deal_ticket": 8100 + len(self.closes), "price": 1995.9,
                  "volume": volume, "retcode": 10009, "filling": "FOK"}
        self.closes.append({"position_ticket": position_ticket,
                            "direction": direction, "volume": volume, **result})
        self.orders = [o for o in self.orders if o["order_ticket"] != position_ticket]
        return result

    def copy_rates(self, symbol, timeframe, count, start_pos=0):
        end = len(self.bars) - start_pos
        return self.bars[max(0, end - count):end]

    def deals_history(self, from_ts, to_ts):
        return []

    def to_utc(self, server_ts):
        return int(server_ts - self.server_offset_sec)


@pytest.fixture()
def fixed_now(monkeypatch):
    monkeypatch.setattr(settings, "utc_now", lambda: FIXED_NOW)


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "JOURNAL_DIR", str(tmp_path / "journal"))
    path = str(tmp_path / "engine.db")
    db.init_db(path)
    return path


def make_engine(tmp_db):
    client = FakeEngineClient()
    engine = Engine(client, pool={"smoke": {"magic": 661901, "timeframe": "M5"}},
                    db_path=tmp_db)
    return engine


class TestSignalPipeline:
    def test_smoke_signal_opened_via_athlete(self, tmp_db, fixed_now):
        """信号 → 门禁放行 → G15 复核 → 开仓登记（signals=opened + trades 行）。"""
        engine = make_engine(tmp_db)
        engine.start()
        stats = engine.force_tick()
        engine.stop()

        assert stats["opened"] == 1
        assert len(engine.client.orders) == 1
        order = engine.client.orders[0]
        assert order["direction"] == "BUY" and order["magic"] == 661901
        assert order["sl"] is not None and order["tp"] is not None   # ATR 兜底
        ro = db.readonly_connect(tmp_db)
        sig = ro.execute("SELECT status, position_ticket FROM signals").fetchone()
        trade = ro.execute("SELECT strategy, direction, entry_price, open_ts"
                           " FROM trades").fetchone()
        ro.close()
        assert sig["status"] == "opened" and sig["position_ticket"] == 9001
        assert trade["strategy"] == "smoke" and trade["direction"] == "BUY"

    def test_exit_flow_journal_and_risk_state(self, tmp_db, fixed_now):
        """开仓 → 策略出场钩子触发 → 平仓 + journal + 风控状态持久化。"""
        engine = make_engine(tmp_db)
        engine.start()
        engine.force_tick()
        engine.strategies[0].check_ema20_exit = lambda *a, **k: True   # 下个 tick 出场
        stats = engine.force_tick()
        engine.stop()

        assert stats["closed"] == 1
        assert len(engine.client.closes) == 1
        assert not engine.athlete.open_entries             # 全平后移出在管表
        # journal：1 行，reason=strategy_exit，pnl_est 有值
        import json
        jpath = os.path.join(settings.JOURNAL_DIR, "closed_trades.jsonl")
        with open(jpath, encoding="utf-8") as f:
            lines = [json.loads(x) for x in f if x.strip()]
        assert len(lines) == 1
        rec = lines[0]
        assert rec["exit_reason"] == "strategy_exit"
        assert rec["position_ticket"] == 9001
        assert rec["pnl"] is not None and rec["pnl_source"] == "local_est"
        # trades 表已写（对账会覆盖 pnl）
        ro = db.readonly_connect(tmp_db)
        trade = ro.execute("SELECT exit_price, exit_reason, close_ts, hold_seconds"
                           " FROM trades").fetchone()
        ro.close()
        assert trade["exit_reason"] == "strategy_exit" and trade["close_ts"] is not None
        # 风控状态已持久化（pnl_est>0 → 同向冷却章 + 连亏清零记录）
        ro = db.readonly_connect(tmp_db)
        n = ro.execute("SELECT COUNT(*) FROM risk_states").fetchone()[0]
        ro.close()
        assert n == 1

    def test_risk_states_reloaded_on_restart(self, tmp_db, fixed_now, monkeypatch):
        """重启恢复：连亏状态从 risk_states 表读回。"""
        from engine.risk import gatekeeper as gk
        engine = make_engine(tmp_db)
        engine.start()
        state = engine.risk_states[661901]
        gk.register_trade_result(state, -5.0)
        gk.register_trade_result(state, -5.0)
        engine._save_risk_state(state)
        engine.stop()

        engine2 = make_engine(tmp_db)
        engine2.start()
        engine2.stop()
        assert engine2.risk_states[661901].consecutive_losses == 2

    def test_safety_lock_voids_signal(self, tmp_db, fixed_now, tmp_path, monkeypatch):
        engine = make_engine(tmp_db)
        engine.start()
        engine.force_tick()
        # 落锁后再扫一次 → 新信号被 G0 拦截
        lock = tmp_path / "safety_lock.txt"
        lock.write_text("locked", encoding="utf-8")
        monkeypatch.setattr(settings, "SAFETY_LOCK_PATH", str(lock))
        engine.force_tick()
        engine.stop()

        ro = db.readonly_connect(tmp_db)
        rows = ro.execute("SELECT status, exit_reason FROM signals"
                          " ORDER BY id").fetchall()
        ro.close()
        assert len(rows) >= 2
        assert rows[-1]["status"] == "voided"
        assert rows[-1]["exit_reason"].startswith("G0")

    def test_indicator_snapshots_written(self, tmp_db, fixed_now):
        engine = make_engine(tmp_db)
        engine.start()
        engine.force_tick()
        engine.stop()
        ro = db.readonly_connect(tmp_db)
        n = ro.execute("SELECT COUNT(*) FROM indicator_snapshots"
                       " WHERE timeframe='M5'").fetchone()[0]
        ro.close()
        assert n > 0
