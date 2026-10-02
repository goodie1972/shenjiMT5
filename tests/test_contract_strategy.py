"""契约测试 — 策略接口（docs/contracts/contract_strategy.md）。

INV-S2 白名单强制（旧库 kiss/goodma 静默 None 教训）+ S-1 六元组形状 +
生命周期钩子存在性。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from strategies.base import BaseStrategy, Candle, INDICATOR_WHITELIST

T0 = 1_700_000_000 - 300 * 30


def make_candles(n=30, step=300):
    """构造升序 K 线；末根 [-1] 是 forming bar，[-2] 是 bar1。"""
    return [Candle(time=T0 + i * step, open=2000.0 + i * 0.1, high=2001.0 + i * 0.1,
                   low=1999.0 + i * 0.1, close=2000.5 + i * 0.1, volume=10 + i)
            for i in range(n)]


def make_provider(candles, indicators):
    def provider(timeframe, count):
        return {"candles": candles[-count:], "indicators": indicators}
    return provider


class DummyStrategy(BaseStrategy):
    name = "dummy"

    def generate_signal(self):
        bar1 = self.bar1()
        rsi = self.get_indicator("rsi")
        if bar1 is not None and bar1.close > bar1.open and (rsi or 50) < 30:
            return ("BUY", 1, 0, ["bar1阳线", "rsi<30"], [], {"rsi": rsi})
        return (None, 0, 0, [], {}, {"rsi": rsi})


class TestWhitelist:
    """INV-S2：未登记键抛错；冻结键表在位。"""

    def test_unknown_key_raises(self):
        s = DummyStrategy(magic=1, timeframe="M30",
                          data_provider=make_provider(make_candles(), {"rsi": 25}))
        s.refresh_data()
        with pytest.raises(KeyError, match="白名单"):
            s.get_indicator("sma_37")          # 旧库 goodma 事故的动态键

    def test_known_key_returns_bar1_value(self):
        s = DummyStrategy(magic=1, timeframe="M30",
                          data_provider=make_provider(make_candles(), {"rsi": 25.5}))
        s.refresh_data()
        assert s.get_indicator("rsi") == 25.5

    def test_frozen_key_inventory(self):
        """56 核心键 + 派生键在位（契约 §4 锁定抽样）。"""
        core = {"rsi", "rsi_5", "rsi_10", "mfi", "bb", "bb_width",
                "ema_9", "ema_21", "ema_34", "ema_50", "ema_200",
                "sma_14", "sma_20", "sma_50", "atr", "atr_20", "adx", "pdi", "ndi",
                "macd", "stoch_5_3_3", "linear_reg_slope", "volume_sma_20", "close",
                "cci", "cci_direction", "wpr", "demarker", "bulls_power", "bears_power",
                "force_index", "obv", "momentum", "std_dev", "sar", "ao", "osma", "ac",
                "bwmfi", "ad", "env_upper", "env_lower", "rvi_main", "rvi_signal",
                "ichi_tenkan", "ichi_kijun", "ichi_senkou_a", "ichi_senkou_b",
                "alligator_jaw", "alligator_teeth", "alligator_lips",
                "gator_upper", "gator_lower", "fractal_upper", "fractal_lower"}
        derived = {"stoch_rsi", "stoch_k_prev", "stoch_d_prev", "candle_pattern_dir",
                   "candle_pattern_name", "bbi", "bb_mid", "bb_mid_direction", "trend",
                   "price_position", "mfi_direction", "rsi_dir_3bar"}   # v1.1: +bb_mid
        assert core <= INDICATOR_WHITELIST
        assert derived <= INDICATOR_WHITELIST
        assert len(INDICATOR_WHITELIST) == len(core) + len(derived)


class TestSixTupleContract:
    """S-1：六元组信号 + on_tick 存储。"""

    def test_on_tick_stores_last_signal(self):
        candles = make_candles()
        indicators = {"rsi": 25.0}
        s = DummyStrategy(magic=1, timeframe="M30",
                          data_provider=make_provider(candles, indicators))
        op = s.on_tick()
        assert s._last_signal["signal"] == "BUY"
        assert s._last_signal["score_long"] == 1
        assert s._last_signal["factors_long"] == ["bar1阳线", "rsi<30"]
        assert "rsi" in s._last_signal["indicator_values"]
        assert op == "Signal: BUY"

    def test_no_signal_shape(self):
        indicators = {"rsi": 60.0}
        s = DummyStrategy(magic=1, timeframe="M30",
                          data_provider=make_provider(make_candles(), indicators))
        assert s.on_tick() is None
        assert s._last_signal["signal"] is None

    def test_insufficient_candles_guard(self):
        s = DummyStrategy(magic=1, timeframe="M30",
                          data_provider=make_provider(make_candles(5), {"rsi": 25}))
        assert s.on_tick() is None           # <10 根守卫

    def test_invalid_signal_rejected(self):
        class Bad(BaseStrategy):
            name = "bad"
            def generate_signal(self):
                return ("LONG", 1, 0, [], {}, {})
        s = Bad(magic=1, timeframe="M30",
                data_provider=make_provider(make_candles(), {"rsi": 25}))
        with pytest.raises(ValueError):
            s.on_tick()

    def test_non_tuple_rejected(self):
        class Bad2(BaseStrategy):
            name = "bad2"
            def generate_signal(self):
                return "BUY"
        s = Bad2(magic=1, timeframe="M30",
                 data_provider=make_provider(make_candles(), {"rsi": 25}))
        with pytest.raises(TypeError):
            s.on_tick()


class TestLifecycleHooks:
    """§5 退出钩子存在且默认安全。"""

    def test_default_hooks(self):
        s = DummyStrategy(magic=1, timeframe="M30",
                          data_provider=make_provider(make_candles(), {"rsi": 25}))
        pos = {"ticket": 123}
        assert s.check_ema20_exit(pos, 2000.0, 2000.2) is False
        assert s.check_partial_exit(pos, 2000.0, 2000.2) == 0.0
        assert s.get_dynamic_sl_tp("BUY", 2000.0) == (None, None)
        assert s.get_adx_data() is None
        assert s._verify_entry({}, 2000.0, {}) is True
        s.mark_extreme_entry(123)            # 不抛即过

    def test_bar1_is_closed_bar(self):
        """INV-S1：bar1() 返回 [-2]（已闭合），不是 forming bar [-1]。"""
        candles = make_candles(30)
        s = DummyStrategy(magic=1, timeframe="M30",
                          data_provider=make_provider(candles, {"rsi": 25}))
        s.refresh_data()
        assert s.bar1().time == candles[-2].time

    def test_data_provider_required(self):
        s = DummyStrategy(magic=1, timeframe="M30")
        with pytest.raises(RuntimeError, match="data_provider"):
            s.refresh_data()
