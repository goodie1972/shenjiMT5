"""m15/m30_followave 移植单测 — 入场四条件、_verify_entry、出场四优先级、
分批止盈、状态冻结。注入 candles + 指标 dict 直接驱动移植代码（逻辑保真验证）。
"""

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from strategies.followave_core import FollowAveCore
from strategies.base import Candle

T0 = 1_800_000_000 - 300 * 60


def mk(n=40, step=1800, base=2000.0):
    """n 根中性 K 线（bar1 在末尾 forming 之前）。"""
    return [Candle(time=T0 + i * step, open=base, high=base + 1, low=base - 1,
                   close=base, volume=100) for i in range(n)]


IND = {  # 默认指标（构造为恰好触发多头：金叉 + +DI 主导 + close 在 BBI 上/中轨上）
    "bbi": 1999.5, "pdi": 25.0, "ndi": 15.0,
    "bb": {"upper": 2010.0, "mid": 2000.0, "lower": 1990.0},
    "stoch_5_3_3": {"k": 56.0, "d": 55.0},
    "stoch_k_prev": 40.0, "stoch_d_prev": 56.0,     # k_prev<=d_prev, k>d → 金叉
    "atr": 4.0, "bb_mid_direction": "NEUTRAL",
}


def make_strat(cls, candles=None, ind=None, trail=3.0):
    s = cls(magic=661402, timeframe="M30")
    if trail != 3.0:
        s.TRAIL_ATR = trail
    s.candles = candles if candles is not None else mk()
    s._cached_indicators = dict(IND if ind is None else ind)
    return s


def pos(direction="BUY", ticket="T1", entry=2000.0, volume=0.01):
    return SimpleNamespace(ticket=ticket, order_type=direction,
                           open_price=entry, volume=volume)


class TestEntry:
    def test_long_all_conditions(self):
        s = make_strat(FollowAveCore)     # IND 已构造金叉 + pdi>ndi + close≥mid
        result = s.generate_signal()
        assert result[0] == "BUY"
        assert result[3] == ["FOLLOWAVE-LONG"]
        assert result[5]["bbi"] == 1999.5

    def test_di_gate_blocks(self):
        ind = dict(IND, pdi=20.0, ndi=19.0)     # diff=1 ≤ 2
        assert make_strat(FollowAveCore, ind=ind).generate_signal() is None

    def test_short_mirror(self):
        ind = dict(IND, pdi=15.0, ndi=25.0,                       # -DI 主导
                   bbi=2000.5,                                    # close(2000) < bbi
                   stoch_5_3_3={"k": 20.5, "d": 21.0},            # k<d（死叉态）
                   stoch_k_prev=35.0, stoch_d_prev=19.0)          # k_prev>=d_prev + k>20
        candles = mk()
        s = make_strat(FollowAveCore, candles=candles, ind=ind)
        result = s.generate_signal()
        assert result[0] == "SELL"
        assert result[4] == ["FOLLOWAVE-SHORT"]

    def test_no_cross_no_entry(self):
        ind = dict(IND, stoch_k_prev=52.0)    # k_prev(52)>d_prev(55)？否——直接构造已金叉态
        ind["stoch_k_prev"] = 60.0            # k_prev>d_prev → 非穿越（早已金叉）
        assert make_strat(FollowAveCore, ind=ind).generate_signal() is None

    def test_k_overbought_blocks_long(self):
        ind = dict(IND, stoch_5_3_3={"k": 85.0, "d": 55.0})
        assert make_strat(FollowAveCore, ind=ind).generate_signal() is None

    def test_missing_indicator_returns_none(self):
        ind = dict(IND, bbi=None)
        assert make_strat(FollowAveCore, ind=ind).generate_signal() is None

    def test_insufficient_candles(self):
        assert make_strat(FollowAveCore, candles=mk(20)).generate_signal() is None


class TestVerifyEntry:
    def test_buy_rejected_below_bbi(self):
        s = make_strat(FollowAveCore)
        cache = {"candles": s.candles, "indicators": s._cached_indicators}
        assert s._verify_entry({"direction": "BUY"}, 1999.0, cache) is False  # < bbi

    def test_buy_rejected_bearish_forming(self):
        s = make_strat(FollowAveCore)
        s.candles[-1] = Candle(time=T0 + 40 * 1800, open=2001.0, high=2002.0,
                               low=1999.0, close=1999.5, volume=1)  # forming 阴线
        cache = {"candles": s.candles, "indicators": s._cached_indicators}
        assert s._verify_entry({"direction": "BUY"}, 2001.0, cache) is False

    def test_buy_accepted(self):
        s = make_strat(FollowAveCore)
        cache = {"candles": s.candles, "indicators": s._cached_indicators}
        assert s._verify_entry({"direction": "BUY"}, 2001.0, cache) is True

    def test_sell_rejected_above_bbi(self):
        ind = dict(IND, pdi=15.0, ndi=25.0, stoch_5_3_3={"k": 30.0, "d": 20.0},
                   stoch_k_prev=35.0, stoch_d_prev=19.0)
        s = make_strat(FollowAveCore, ind=ind)
        cache = {"candles": s.candles, "indicators": s._cached_indicators}
        assert s._verify_entry({"direction": "SELL"}, 2001.0, cache) is False
        assert s._verify_entry({"direction": "SELL"}, 1999.0, cache) is True


class TestExits:
    def _open(self, s, direction="BUY", entry=2000.0, ticket="T1"):
        s.mark_extreme_entry(ticket)
        return pos(direction, ticket, entry)

    def test_partial_tp_once(self):
        s = make_strat(FollowAveCore)
        p = self._open(s, "BUY", 2000.0)                     # partial_atr=4.0 → 触发 2012
        candles = mk()
        candles[-2] = Candle(time=candles[-2].time, open=2010, high=2013,
                             low=2009, close=2012.0, volume=1)  # bar1 close=2012
        s.candles = candles
        assert s.check_partial_exit(p, 2012, 2012.2) == 0.5
        assert s.check_partial_exit(p, 2013, 2013.2) == 0.0  # 每笔仅一次

    def test_partial_not_reached(self):
        s = make_strat(FollowAveCore)
        p = self._open(s, "BUY", 2000.0)
        assert s.check_partial_exit(p, 2005, 2005.2) == 0.0

    def test_trend_reversal_needs_three_bars(self):
        s = make_strat(FollowAveCore)
        p = self._open(s, "BUY")
        s._cached_indicators = dict(IND, bbi=2000.0, bb_mid_direction="DOWN")
        base_t = s.candles[-2].time
        fired = False
        for i, close in enumerate([1998.0, 1997.0, 1996.0]):  # 连续 3 根 close<bbi
            s.candles[-2] = Candle(time=base_t + i * 1800, open=1999, high=1999.5,
                                   low=1995, close=close, volume=1)
            fired = s.check_ema20_exit(p, close, close + 0.2)
            if i < 2:
                assert fired is False
        assert fired is True
        assert s._last_exit_detail["exit_type"] == "trend_reversal"

    def test_trend_reversal_resets_on_break(self):
        s = make_strat(FollowAveCore)
        p = self._open(s, "BUY")
        t0 = s.candles[-2].time
        s.candles[-2] = Candle(time=t0, open=2000, high=2001, low=1999,
                               close=2000.0, volume=1)          # 中性 bar：不计数
        assert s.check_ema20_exit(p, 2000, 2000.2) is False
        s._exit_state["T1"]["exit_count"] = 2
        # 方向不配合（close<bbi 但 bb_mid_direction=UP）→ 计数清零
        s._cached_indicators = dict(IND, bbi=2000.0, bb_mid_direction="UP")
        s.candles[-2] = Candle(time=t0 + 1800, open=2000, high=2001, low=1998,
                               close=1999.5, volume=1)
        assert s.check_ema20_exit(p, 1999.5, 1999.7) is False
        assert s._exit_state["T1"]["exit_count"] == 0

    def test_bb_hard_stop(self):
        s = make_strat(FollowAveCore)
        p = self._open(s, "BUY")
        ind = dict(IND, bb={"upper": 2010.0, "mid": 2000.0, "lower": 1990.0})
        s._cached_indicators = ind
        s.candles[-2] = Candle(time=s.candles[-2].time, open=1991, high=1992,
                               low=1988, close=1989.0, volume=1)  # close < lower
        assert s.check_ema20_exit(p, 1989, 1989.2) is True
        assert s._last_exit_detail["exit_type"] == "bb_hard_stop"

    def test_trailing_stop(self):
        s = make_strat(FollowAveCore, trail=3.0)
        p = self._open(s, "BUY")
        # 先一根冲高（peak=2020）
        s.candles[-2] = Candle(time=s.candles[-2].time, open=2010, high=2020,
                               low=2009, close=2018, volume=1)
        assert s.check_ema20_exit(p, 2018, 2018.2) is False
        # 再一根回撤：close < peak − 3×ATR = 2020 − 12 = 2008
        s.candles[-2] = Candle(time=s.candles[-2].time + 1800, open=2010, high=2011,
                               low=2005, close=2007.0, volume=1)
        assert s.check_ema20_exit(p, 2007, 2007.2) is True
        assert s._last_exit_detail["exit_type"] == "trail_stop"
        assert s._last_exit_detail["peak"] == 2020.0

    def test_stoch_cross_tp_requires_bb_touch(self):
        s = make_strat(FollowAveCore)
        p = self._open(s, "BUY")
        t0 = s.candles[-2].time
        # 死叉 + K>80，但未触 BB 上轨 → 不触发
        s._cached_indicators = dict(IND, stoch_5_3_3={"k": 82.0, "d": 85.0},
                                    stoch_k_prev=86.0, stoch_d_prev=84.0)
        assert s.check_ema20_exit(p, 2005, 2005.2) is False
        # 触碰上轨（high ≥ upper−3 = 2007）后死叉 → 触发（新 bar1 时间避开冻结）
        s.candles[-2] = Candle(time=t0 + 1800, open=2006, high=2008,
                               low=2005, close=2007, volume=1)
        assert s.check_ema20_exit(p, 2007, 2007.2) is True
        assert s._last_exit_detail["exit_type"] == "stoch_cross_tp"

    def test_state_freeze_same_bar_once(self):
        """INV-S1.4：同一根闭合 K 线只处理一次。"""
        s = make_strat(FollowAveCore)
        p = self._open(s, "BUY")
        s.candles[-2] = Candle(time=s.candles[-2].time, open=1991, high=1992,
                               low=1988, close=1989.0, volume=1)  # 触发 BB 硬止损
        assert s.check_ema20_exit(p, 1989, 1989.2) is True
        assert s.check_ema20_exit(p, 1989, 1989.2) is False  # 同 bar 二次调用冻结


class TestOnTickPath:
    """回归：移植策略必须能走完引擎 on_tick 全路径（影子运行曾暴露 None 被误杀）。"""

    def _engine_ready(self, cls, ind):
        s = cls(magic=661402, timeframe="M30")
        s.data_provider = lambda tf, count: {"candles": mk(), "indicators": dict(ind)}
        return s

    def test_no_signal_returns_none_without_error(self):
        ind = dict(IND, stoch_k_prev=60.0)      # 非穿越 → generate_signal 返回 None
        s = self._engine_ready(FollowAveCore, ind)
        assert s.on_tick() is None              # v1.1 会在这里抛 TypeError
        assert s._last_signal is None

    def test_signal_stored_via_on_tick(self):
        s = self._engine_ready(FollowAveCore, IND)
        assert s.on_tick() == "Signal: BUY"
        assert s._last_signal["signal"] == "BUY"
        assert s._last_signal["factors_long"] == ["FOLLOWAVE-LONG"]

    def test_insufficient_candles_via_provider(self):
        s = FollowAveCore(magic=661402, timeframe="M30")
        s.data_provider = lambda tf, count: {"candles": mk(15), "indicators": dict(IND)}
        assert s.on_tick() is None              # <10 根守卫（15 根够 on_tick 但 <30 由策略返回 None）


class TestSLTP:
    def test_wide_fallback(self):
        s = make_strat(FollowAveCore)
        sl, tp = s.get_dynamic_sl_tp("BUY", 2000.0, atr_val=4.0)
        assert sl == pytest.approx(2000.0 - max(12.0, 30.0))   # max(3×ATR, 30)
        assert tp == 0                                          # 无 TP，出场全托管
        sl2, _ = s.get_dynamic_sl_tp("SELL", 2000.0, atr_val=20.0)
        assert sl2 == pytest.approx(2000.0 + 60.0)

    def test_m15_m30_params(self):
        """薄壳参数：M30=3.0 / M15=4.0（旧库 v1.2 定值），magic 沿用旧号段。"""
        import importlib
        m30 = importlib.import_module("strategies.20261002_m30_followave_v1")
        m15 = importlib.import_module("strategies.20261002_m15_followave_v1")
        assert m30.M30FollowAveStrategy.TRAIL_ATR == 3.0
        assert m30.M30FollowAveStrategy.name == "m30_followave"
        assert m30.STRATEGY_MAGIC == 661402
        assert m15.M15FollowAveStrategy.TRAIL_ATR == 4.0
        assert m15.M15FollowAveStrategy.name == "m15_followave"
        assert m15.STRATEGY_MAGIC == 661401
