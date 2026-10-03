"""core/mt5_client 单测 — 用注入的 fake MT5 模块脱离终端验证（T0.6 验收）。

覆盖：filling 自适应选择、offset 校准与 to_utc fail-closed、symbol spec 缓存与
pip 推导、下单请求组装（价格侧/填充策略/retcode 校验）。
"""

import os
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.mt5_client import MT5Client, MT5Error, select_filling


class FakeMT5:
    """最小 fake：只实现 client 用到的常量与函数。"""

    TRADE_ACTION_DEAL = 1
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_FOK = 0
    ORDER_FILLING_IOC = 1
    ORDER_FILLING_RETURN = 2
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_DONE_PARTIAL = 10010
    TRADE_RETCODE_PLACED = 10008
    TIMEFRAME_M1 = "M1"

    def __init__(self, tick_time, bid=2000.0, ask=2000.1):
        self._tick_time = tick_time
        self._tick = SimpleNamespace(time=tick_time, bid=bid, ask=ask, last=0.0, volume=0)
        self._spec = SimpleNamespace(
            digits=2, point=0.01, volume_min=0.01, volume_step=0.01, volume_max=100.0,
            trade_tick_value=0.1, trade_tick_size=0.01, trade_stops_level=0,
            trade_freeze_level=0, filling_mode=3, trade_mode=4)
        self.last_error_ret = ("ok", 0)
        self.sent_requests = []
        self._send_result = SimpleNamespace(
            retcode=10009, order=9001, deal=8001, price=2000.1, volume=0.01, comment="done")

    def initialize(self, **kwargs):
        return True

    def shutdown(self):
        pass

    def terminal_info(self):
        return SimpleNamespace(name="FakeMT5", build=6231, path="fake", data_path="fake")

    def version(self):
        return (500, 6231, "2026-10-01")

    def account_info(self):
        return SimpleNamespace(login=113526190, server="Fake-Demo", currency="USD",
                               balance=100000.0, equity=100000.0, trade_allowed=True,
                               margin_mode=2)

    def symbol_select(self, symbol, enable):
        return True

    def symbol_info(self, symbol):
        return self._spec

    def symbol_info_tick(self, symbol):
        return self._tick

    def last_error(self):
        return self.last_error_ret

    def order_send(self, request):
        self.sent_requests.append(request)
        return self._send_result

    def set_server_time(self, ts):
        self._tick.time = ts


def make_client(server_ts=None):
    fake = FakeMT5(tick_time=server_ts if server_ts else int(time.time()) + 10800)
    client = MT5Client(mt5_module=fake)
    return client, fake


class TestSelectFilling:
    """D6：掩码自适应，FOK → IOC → RETURN。"""

    def test_priority(self):
        assert select_filling(3) == "FOK"      # FOK|IOC → FOK 优先
        assert select_filling(2) == "IOC"
        assert select_filling(4) == "RETURN"
        assert select_filling(7) == "FOK"

    def test_zero_mask_rejects(self):
        with pytest.raises(MT5Error, match="filling"):
            select_filling(0)                   # fail-closed


class TestTimezone:
    """D1：offset 实测；to_utc 未校准即拒绝（fail-closed）。"""

    def test_to_utc_requires_calibration(self):
        client = MT5Client(mt5_module=FakeMT5(0))
        client.server_offset_sec = None
        client._load_persisted_offset = lambda: None
        client.server_offset_sec = None
        with pytest.raises(MT5Error, match="未校准"):
            client.to_utc(1_000_000)

    def test_calibrate_and_convert(self):
        now = int(time.time())
        fake = FakeMT5(tick_time=now + 10800)          # 服务器快 3 小时
        client = MT5Client(mt5_module=fake)
        client._persist_offset = lambda: None           # 测试不落盘
        client.server_offset_sec = None
        offset = client.calibrate_offset()
        assert abs(offset - 10800.0) <= 2               # 秒级取整误差容忍
        assert client.to_utc(now + 10800) == now

    def test_calibrate_immune_to_stale_tick(self):
        """影子运行实测回归：tick 陈旧 49s 不得烧进偏移（bar-open 法优先）。"""
        now = int(time.time())
        fake = FakeMT5(tick_time=now + 10800 - 49)      # 最后 tick 陈旧 49 秒
        # M1 forming bar 开盘 = 当前分钟起点（server 域）
        fake.bars = [{"time": (now // 60) * 60 + 10800}]
        fake._rates = fake.bars

        def copy_rates_from_pos(symbol, tf, pos, count):
            return fake._rates[pos:pos + count]

        fake.copy_rates_from_pos = copy_rates_from_pos
        client = MT5Client(mt5_module=fake)
        client._persist_offset = lambda: None
        client.server_offset_sec = None
        offset = client.calibrate_offset()
        assert offset == 10800.0                        # 精确值，无 -49 抖动

    def test_closed_market_keeps_persisted_offset(self):
        """休市实测回归：tick/bar 全部陈旧时保持持久值（曾把 -13080s 持久化）。"""
        now = int(time.time())
        closed_tick = now + 10800 - 5 * 3600            # 最后 tick = 5 小时前（周五收盘）
        fake = FakeMT5(tick_time=closed_tick)
        fake.bars = [{"time": closed_tick - 59}]        # M1 bar 同样陈旧
        fake._rates = fake.bars

        def copy_rates_from_pos(symbol, tf, pos, count):
            return fake._rates[pos:pos + count]

        fake.copy_rates_from_pos = copy_rates_from_pos
        client = MT5Client(mt5_module=fake)
        client._persist_offset = lambda: None
        client.server_offset_sec = 10800.0              # 周五开市时验证过的持久值
        offset = client.calibrate_offset()
        assert offset == 10800.0                        # 保持，不被休市垃圾改写


class TestSymbolSpec:
    def test_spec_cached_and_pip_derived(self):
        client, fake = make_client()
        spec = client.symbol_spec("XAUUSD")
        assert spec["digits"] == 2 and spec["pip_size"] == 0.01
        # 三位报价品种 → pip = 10*point
        fake._spec.digits = 3
        fake._spec.point = 0.001
        spec3 = client.symbol_spec("EURUSD")
        assert spec3["pip_size"] == 0.01
        assert client.symbol_spec("XAUUSD") is client._symbol_specs["XAUUSD"]  # 缓存


class TestOrderSend:
    def _client(self):
        client, fake = make_client()
        client.symbol_spec("XAUUSD")
        return client, fake

    def test_buy_request_shape(self):
        client, fake = self._client()
        r = client.order_send("XAUUSD", "BUY", 0.01, sl=1990.0, magic=661402)
        req = fake.sent_requests[0]
        assert req["type"] == fake.ORDER_TYPE_BUY
        assert req["price"] == 2000.1                       # BUY 吃 ask
        assert req["sl"] == 1990.0 and req["tp"] == 0.0
        assert req["magic"] == 661402
        assert req["type_filling"] == fake.ORDER_FILLING_FOK  # 掩码 3 → FOK
        assert r["filling"] == "FOK" and r["order_ticket"] == 9001

    def test_sell_uses_bid(self):
        client, fake = self._client()
        client.order_send("XAUUSD", "SELL", 0.02)
        assert fake.sent_requests[0]["type"] == fake.ORDER_TYPE_SELL
        assert fake.sent_requests[0]["price"] == 2000.0

    def test_rejected_retcode_raises(self):
        client, fake = self._client()
        fake._send_result = SimpleNamespace(retcode=10030, order=0, deal=0,
                                            price=0.0, volume=0.0, comment="invalid fill")
        with pytest.raises(MT5Error, match="10030"):
            client.order_send("XAUUSD", "BUY", 0.01)
