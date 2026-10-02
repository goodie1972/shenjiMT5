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
    """引擎所需的最小 fake：行情 + 账户 + 持仓。"""

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
        self._lock_file = None

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
        return []

    def copy_rates(self, symbol, timeframe, count, start_pos=0):
        end = len(self.bars) - start_pos
        return self.bars[max(0, end - count):end]

    def to_utc(self, server_ts):
        return int(server_ts - self.server_offset_sec)


@pytest.fixture()
def fixed_now(monkeypatch):
    monkeypatch.setattr(settings, "utc_now", lambda: FIXED_NOW)


@pytest.fixture()
def tmp_db(tmp_path):
    path = str(tmp_path / "engine.db")
    db.init_db(path)
    return path


def make_engine(tmp_db):
    client = FakeEngineClient()
    engine = Engine(client, pool={"smoke": {"magic": 661901, "timeframe": "M5"}},
                    db_path=tmp_db)
    return engine


class TestSignalPipeline:
    def test_smoke_signal_recorded_pending(self, tmp_db, fixed_now):
        engine = make_engine(tmp_db)
        engine.start()
        stats = engine.force_tick()
        engine.stop()

        ro = db.readonly_connect(tmp_db)
        rows = ro.execute("SELECT strategy, magic, direction, status, score_long,"
                          " factors_long FROM signals").fetchall()
        ro.close()
        assert len(rows) >= 1
        r = rows[-1]
        assert r["strategy"] == "smoke" and r["magic"] == 661901
        assert r["direction"] == "BUY"
        assert r["status"] == "pending"        # 全门禁放行 → pending（等 Athlete T1.3）
        assert r["score_long"] == 1
        assert "rsi" in r["factors_long"]

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
