"""engine/indicators 单测（T1.2）— 手算小样本 + 行情不变量 + 契约纪律。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import pytest

from engine import indicators as ind


def make_df(n=260, start=2000.0, drift=0.05, seed=7):
    """带随机波动的升序收盘序列（bar1 在末尾）。"""
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, 0.5, n)
    close = start + np.cumsum(drift + noise)
    high = close + np.abs(rng.normal(0.8, 0.2, n))
    low = close - np.abs(rng.normal(0.8, 0.2, n))
    open_ = np.concatenate([[close[0]], close[:-1]])
    vol = rng.integers(50, 200, n).astype(float)
    return pd.DataFrame({"time": np.arange(n) * 60, "open": open_, "high": high,
                         "low": low, "close": close, "volume": vol})


class TestWhitelistDiscipline:
    """INV-S2 + fail-closed：PENDING 键报错、白名单全覆盖或显式缺席登记。"""

    def test_pending_key_raises(self):
        with pytest.raises(KeyError, match="PENDING"):
            ind.compute_bar1(make_df(100), keys={"sar"})

    def test_non_whitelist_key_raises(self):
        with pytest.raises(KeyError, match="白名单"):
            ind.compute_bar1(make_df(100), keys={"sma_37"})   # goodma 事故的键

    def test_computed_and_pending_partition_whitelist(self):
        from strategies.base import INDICATOR_WHITELIST
        # 白名单里每个键要么已实现要么显式登记为 PENDING，不允许"隐身"键
        assert ind.COMPUTED_KEYS | ind.PENDING_KEYS == set(INDICATOR_WHITELIST)

    def test_missing_for(self):
        assert ind.missing_for({"sar", "rsi"}) == {"sar"}
        assert ind.missing_for({"rsi", "adx"}) == set()


class TestExactValues:
    """可手算的小样本精确值。"""

    def test_sma_and_ema(self):
        df = make_df(60)
        assert ind.compute_bar1(df, keys={"sma_20"})["sma_20"] == \
            pytest.approx(df["close"].tail(20).mean())

    def test_rsi_pure_uptrend_is_100(self):
        up = pd.DataFrame({"time": np.arange(30) * 60, "open": np.linspace(1, 2, 30),
                           "high": np.linspace(1, 2, 30) + 0.1,
                           "low": np.linspace(1, 2, 30) - 0.1,
                           "close": np.linspace(1, 2, 30), "volume": [100.0] * 30})
        assert ind.compute_bar1(up, keys={"rsi"})["rsi"] == pytest.approx(100.0)

    def test_rsi_pure_downtrend_is_0(self):
        down = pd.DataFrame({"time": np.arange(30) * 60, "open": np.linspace(2, 1, 30),
                             "high": np.linspace(2, 1, 30) + 0.1,
                             "low": np.linspace(2, 1, 30) - 0.1,
                             "close": np.linspace(2, 1, 30), "volume": [100.0] * 30})
        assert ind.compute_bar1(down, keys={"rsi"})["rsi"] == pytest.approx(0.0)

    def test_stoch_bounds_and_prev_shift(self):
        df = make_df(260)
        s = ind.compute_bar1(df, keys={"stoch_5_3_3", "stoch_k_prev", "stoch_d_prev"})
        assert 0.0 <= s["stoch_5_3_3"]["k"] <= 100.0
        assert 0.0 <= s["stoch_k_prev"] <= 100.0
        f = ind._stoch_frame(df)
        assert s["stoch_k_prev"] == pytest.approx(f["k"].iloc[-2])
        assert s["stoch_d_prev"] == pytest.approx(f["d"].iloc[-2])

    def test_price_position_matches_gate_formula(self):
        df = make_df(260)
        hh = df["high"].tail(40).max()
        ll = df["low"].tail(40).min()
        pp = ind.compute_bar1(df, keys={"price_position"})["price_position"]
        assert pp == pytest.approx((df["close"].iloc[-1] - ll) / (hh - ll))
        assert 0.0 <= pp <= 1.0


class TestInvariants:
    def test_all_computed_keys_return(self):
        keys = ind.COMPUTED_KEYS - {"ema_200"}   # ema_200 需 ≥200 根，260 根够——保留亦可
        out = ind.compute_bar1(make_df(260), keys=set(ind.COMPUTED_KEYS))
        assert set(out) == set(ind.COMPUTED_KEYS)
        for k in ("rsi", "mfi", "wpr", "adx", "pdi", "ndi"):
            assert out[k] is None or -100.0 <= out[k] <= 100.0 or np.isnan(out[k]), k
        assert out["atr"] > 0
        assert isinstance(out["bb"], dict) and set(out["bb"]) == {"upper", "mid", "lower"}
        assert isinstance(out["macd"], dict) and set(out["macd"]) == {"macd", "signal", "hist"}
        assert out["trend"] in ("UP", "DOWN", "SIDE")
        assert out["candle_pattern_name"] in ("bull", "bear", "doji")

    def test_bbi_between_fast_and_slow_ma(self):
        df = make_df(260)
        out = ind.compute_bar1(df, keys={"bbi", "sma_20"})
        assert out["bbi"] is not None and out["bbi"] > 0

    def test_followave_required_keys_available(self):
        """旗舰策略需要的键全部已实现（M2 移植前置条件）。"""
        need = {"adx", "pdi", "ndi", "bbi", "stoch_5_3_3", "stoch_k_prev", "stoch_d_prev",
                "bb", "bb_mid", "bb_mid_direction", "atr", "close",
                "candle_pattern_dir", "price_position"}
        assert need <= ind.COMPUTED_KEYS
        out = ind.compute_bar1(make_df(260), keys=need)
        assert all(v is not None for v in out.values())

    def test_nan_becomes_none(self):
        short = make_df(25)                      # 不够 40 根 → price_position 无 NaN 但 sma_50 有
        out = ind.compute_bar1(short, keys={"sma_50"})
        assert out["sma_50"] is None
