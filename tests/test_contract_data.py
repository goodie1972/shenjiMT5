"""契约测试 — 数据规范（docs/contracts/contract_data.md）。"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from data import database as db


@pytest.fixture()
def tmp_db(tmp_path):
    path = str(tmp_path / "test.db")
    db.init_db(path)
    return path


CANDLE = {"timestamp": 1_700_000_000, "open": 2000.0, "high": 2001.0,
          "low": 1999.0, "close": 2000.5, "volume": 123}


class TestOhlcvSchema:
    """契约 §2：六列 + PK(timeframe, timestamp) + UTC 秒语义。"""

    def test_columns_and_pk(self, tmp_db):
        conn = sqlite3.connect(tmp_db)
        cols = {r[1]: r for r in conn.execute("PRAGMA table_info(ohlcv)")}
        assert set(cols) == {"timeframe", "timestamp", "open", "high", "low", "close", "volume"}
        pk = [r[1] for r in sorted(cols.values(), key=lambda r: r[5]) if r[5] > 0]
        assert pk == ["timeframe", "timestamp"]

    def test_upsert_idempotent_replace(self, tmp_db):
        db.upsert_candles("M5", [CANDLE], db_path=tmp_db)
        newer = dict(CANDLE, close=2001.75)
        db.upsert_candles("M5", [newer], db_path=tmp_db)
        rows = db.get_candles("M5", db_path=tmp_db)
        assert len(rows) == 1                 # PK 幂等：同 (tf, ts) 覆盖不新增
        assert rows[0]["close"] == 2001.75

    def test_timeframe_whitelist(self, tmp_db):
        with pytest.raises(ValueError):
            db.upsert_candles("M7", [CANDLE], db_path=tmp_db)
        with pytest.raises(ValueError):
            db.get_candles("M7", db_path=tmp_db)

    def test_readonly_connect_refuses_write(self, tmp_db):
        conn = db.readonly_connect(tmp_db)
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO ohlcv VALUES ('M5',1,1,1,1,1,1)")
        conn.close()

    def test_table_whitelist_on_read(self, tmp_db):
        with pytest.raises(ValueError):
            db.get_candles("M5", table="sqlite_master", db_path=tmp_db)


class TestLayering:
    """契约 §1：工具只读打开（mode=ro + query_only 双保险）。"""

    def test_readonly_uri_mode(self, tmp_db):
        conn = db.readonly_connect(tmp_db)
        assert conn.execute("PRAGMA query_only").fetchone()[0] == 1
        conn.close()

    def test_aux_tables_exist(self, tmp_db):
        """signals/trades/risk_states/indicator_snapshots 骨架表就位。"""
        conn = sqlite3.connect(tmp_db)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"ohlcv", "signals", "trades", "risk_states",
                "indicator_snapshots"} <= tables
        conn.close()


class TestUtcConvention:
    """契约 §3：时间戳是 UTC 秒 int64 —— 由调用方转换，库不校验语义但 schema 声明 INTEGER。

    这里锁定"调用方约定"：config.settings 只提供 UTC 口径的时间函数。
    """

    def test_settings_time_helpers_are_utc(self):
        from datetime import timezone
        from config import settings
        ts = 1_700_000_000
        assert settings.utc_dt(ts).utcoffset() == timezone.utc.utcoffset(None)
        # local_dt 仅显示层：偏移固定 UTC+8
        assert settings.local_dt(ts).utcoffset().total_seconds() == 8 * 3600
