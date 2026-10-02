"""engine/data_factory 测试 — T0.7 契约验证（fake client 脱离终端）。

contract_data §2（UTC 入库）+ §7（forming bar 不入库）。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from config import settings
from engine import data_factory

SERVER_OFFSET = 10800          # 假服务器快 3 小时（实测 +3.00h）
STEP = 300                     # M5


class FakeClient:
    """fake client：copy_rates 返回 server-time 行；to_utc 按 offset 换算。"""

    def __init__(self, n_bars, end_server_ts=1_800_000_000):
        self.server_offset_sec = float(SERVER_OFFSET)
        bars = []
        for i in range(n_bars):
            ts = end_server_ts - (n_bars - 1 - i) * STEP
            bars.append({"time": ts, "open": 2000.0 + i * 0.01, "high": 2001.0,
                         "low": 1999.0, "close": 2000.5, "volume": 10 + i})
        self.bars = bars

    def copy_rates(self, symbol, timeframe, count, start_pos=0):
        # 模拟终端 copy_rates_from_pos：pos 0 = 最新 forming bar，升序返回
        end = len(self.bars) - start_pos
        begin = max(0, end - count)
        return self.bars[begin:end]

    def to_utc(self, server_ts):
        return int(server_ts - self.server_offset_sec)


@pytest.fixture()
def tmp_db(tmp_path):
    from data import database as db
    path = str(tmp_path / "t.db")
    db.init_db(path)
    return path


class TestFormingBarExclusion:
    def test_forming_bar_not_ingested(self, tmp_db):
        client = FakeClient(n_bars=10)
        n = data_factory.pull_timeframe(client, "M5", count=10, db_path=tmp_db)
        assert n == 9                       # 末根 forming bar 丢弃
        from data import database as db
        last = db.get_candles("M5", db_path=tmp_db)[-1]
        assert last["timestamp"] == client.bars[-2]["time"] - SERVER_OFFSET

    def test_utc_conversion_applied(self, tmp_db):
        from data import database as db
        client = FakeClient(n_bars=10)
        data_factory.pull_timeframe(client, "M5", count=10, db_path=tmp_db)
        rows = db.get_candles("M5", db_path=tmp_db)
        for row, server_bar in zip(rows, client.bars[:-1]):
            assert row["timestamp"] == server_bar["time"] - SERVER_OFFSET   # UTC = server − offset

    def test_idempotent_rerun(self, tmp_db):
        from data import database as db
        client = FakeClient(n_bars=10)
        n1 = data_factory.pull_timeframe(client, "M5", count=10, db_path=tmp_db)
        n2 = data_factory.pull_timeframe(client, "M5", count=10, db_path=tmp_db)
        assert n1 == n2 == 9
        assert len(db.get_candles("M5", db_path=tmp_db)) == 9   # PK 幂等，不重复

    def test_unknown_tf_rejected(self, tmp_db):
        client = FakeClient(n_bars=10)
        with pytest.raises(ValueError):
            data_factory.pull_timeframe(client, "M7", count=10, db_path=tmp_db)


class TestBackfillPaging:
    """分页回填：首页砍 forming bar，逐页向历史翻，取不满一页即停。"""

    def test_pages_and_no_overlap(self, tmp_db):
        from data import database as db
        client = FakeClient(n_bars=120)                    # 120 根，页 50 → 3 页耗尽
        n = data_factory.backfill(client, "M5", max_pages=5,
                                  page_size=50, db_path=tmp_db)
        assert n == 119                                    # 120 − 1 forming
        rows = db.get_candles("M5", db_path=tmp_db)
        assert len(rows) == 119
        assert len({r["timestamp"] for r in rows}) == 119  # 无重复
        times = [r["timestamp"] for r in rows]
        assert times == sorted(times)                      # 升序连续

    def test_stops_at_page_cap(self, tmp_db):
        from data import database as db
        client = FakeClient(n_bars=300)
        n = data_factory.backfill(client, "M5", max_pages=2,
                                  page_size=50, db_path=tmp_db)
        assert n == 99                                     # 2 页 × 50 − 首页 forming bar
        assert len(db.get_candles("M5", db_path=tmp_db)) == 99


class TestCacheProvider:
    """build_cache：DB 闭合序列 + forming bar 拼尾 + 指标 + 快照落库。"""

    def test_cache_bar0_bar1_positions_and_utc(self, tmp_db):
        from data import database as db
        client = FakeClient(n_bars=30)
        data_factory.pull_timeframe(client, "M5", count=30, db_path=tmp_db)
        cache = data_factory.build_cache(client, "M5", lookback=100, db_path=tmp_db)
        candles = cache["candles"]
        assert len(candles) == 30                    # 29 闭合 + 1 forming
        assert candles[-2].time == client.bars[-2]["time"] - SERVER_OFFSET   # bar1
        assert candles[-1].time == client.bars[-1]["time"] - SERVER_OFFSET   # bar0
        assert candles[0].time < candles[-1].time                             # 升序

    def test_cache_indicators_and_snapshot(self, tmp_db):
        from data import database as db
        client = FakeClient(n_bars=30)
        data_factory.pull_timeframe(client, "M5", count=30, db_path=tmp_db)
        cache = data_factory.build_cache(client, "M5", lookback=100, db_path=tmp_db)
        assert isinstance(cache["indicators"], dict) and cache["indicators"]
        assert "rsi" in cache["indicators"]          # 指标引擎已接入
        row = db.readonly_connect(tmp_db).execute(
            "SELECT COUNT(*) FROM indicator_snapshots WHERE timeframe='M5'").fetchone()
        assert row[0] > 0                            # 快照已落库
