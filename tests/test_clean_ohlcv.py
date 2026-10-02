"""tools/clean_ohlcv 三规则单测（contract_data §6）— 合成数据直接驱动 assess_tf。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from tools.clean_ohlcv import aggregate_m1, assess_tf, detect_offset

STEP = 900                      # M15
OFFSET = 0
T0 = 1_800_000_000 // STEP * STEP   # 对齐桶起点


def make_m1(n_minutes, start=T0, price=2000.0):
    """连续 M1：每根涨 0.01，volume=1。"""
    return pd.DataFrame({
        "time": [start + i * 60 for i in range(n_minutes)],
        "open": [price + i * 0.01 for i in range(n_minutes)],
        "high": [price + i * 0.01 + 0.5 for i in range(n_minutes)],
        "low": [price + i * 0.01 - 0.5 for i in range(n_minutes)],
        "close": [price + i * 0.01 for i in range(n_minutes)],
        "volume": [1] * n_minutes,
    })


def row(ts, o=2000.0, h=2001.0, l=1999.0, c=2000.0, v=15):
    return {"time": ts, "open": o, "high": h, "low": l, "close": c, "volume": v}


class TestAggregate:
    def test_bucket_shape(self):
        m1 = make_m1(30)                          # 恰好 2 个 M15 桶
        agg = aggregate_m1(m1, STEP, OFFSET)
        assert len(agg) == 2
        assert list(agg.columns) == ["time", "open", "high", "low", "close", "volume"]
        assert agg["volume"].tolist() == [15, 15]
        assert agg["open"].iloc[0] == 2000.0 and agg["close"].iloc[0] == 2000.14


def m1_with_hole(n_minutes=30, hole_start_bucket=1):
    """中间桶整桶开洞的 M1（洞 = 目标 TF 有 bar 而 M1 零覆盖 → ghost 的成因）。"""
    m1 = make_m1(n_minutes)
    drop = [T0 + hole_start_bucket * STEP + i * 60 for i in range(STEP // 60)]
    return m1[~m1["time"].isin(drop)].reset_index(drop=True)


class TestRules:
    def test_ghost_detected_and_deleted(self):
        m1 = m1_with_hole(30)                     # 覆盖 T0..T0+1740，但 T0+900 桶零覆盖
        tgt = pd.DataFrame([row(T0), row(T0 + 900),
                            row(T0 + 1800)])      # T0+1800 超出覆盖 → 透传不算 ghost
        r = assess_tf(tgt, aggregate_m1(m1, STEP, OFFSET), STEP,
                      T0, T0 + 1740, 0.005, "ohlc", "delete")
        assert r["ghosts"] == [T0 + 900]
        assert T0 + 900 not in set(r["final"]["time"])      # delete 策略已删
        assert T0 + 1800 in set(r["final"]["time"])         # 窗口外透传

    def test_ghost_kept_for_h4_policy(self):
        m1 = m1_with_hole(30)
        tgt = pd.DataFrame([row(T0), row(T0 + 900)])
        r = assess_tf(tgt, aggregate_m1(m1, STEP, OFFSET), STEP,
                      T0, T0 + 1740, 0.005, "ohlc", "keep")
        assert r["ghosts"] == [T0 + 900]
        assert T0 + 900 in set(r["final"]["time"])          # keep 策略保留

    def test_deviation_rebuild(self):
        m1 = make_m1(30)
        bad = row(T0, c=2100.0)                   # close 偏差 ~5% ≫ 0.5%
        bad.update(o=2100.0, h=2101.0, l=2099.0)
        tgt = pd.DataFrame([bad, row(T0 + 900)])
        r = assess_tf(tgt, aggregate_m1(m1, STEP, OFFSET), STEP,
                      T0, T0 + 1799, 0.005, "ohlc", "delete")
        assert r["rebuilds"] == [T0]
        fixed = r["final"].set_index("time").loc[T0]
        assert abs(fixed["close"] - 2000.14) < 1e-9         # 已被聚合值重建

    def test_reverse_gap_filled(self):
        m1 = make_m1(45)                          # 覆盖 3 个桶
        tgt = pd.DataFrame([row(T0), row(T0 + 1800)])   # 缺中间桶 T0+900
        r = assess_tf(tgt, aggregate_m1(m1, STEP, OFFSET), STEP,
                      T0, T0 + 2699, 0.005, "ohlc", "delete")
        assert r["fills"] == 1
        assert T0 + 900 in set(r["final"]["time"])

    def test_forming_bucket_not_assessed(self):
        """右端未闭合桶（forming）：不评估、不补洞（never fabricate）。"""
        m1 = make_m1(25)                          # 末桶 T0+1800 只有 5 根 M1，未闭合
        tgt = pd.DataFrame([row(T0), row(T0 + 900)])    # 目标缺未闭合桶
        r = assess_tf(tgt, aggregate_m1(m1, STEP, OFFSET), STEP,
                      T0, T0 + 1799, 0.005, "ohlc", "delete")
        assert r["fills"] == 0                    # 未闭合桶不补
        assert r["rebuilds"] == []


class TestDetectOffset:
    def test_mode_detection(self):
        ts = [T0 + i * STEP for i in range(100)]
        off, ratio = detect_offset(ts, STEP)
        assert off == T0 % STEP == 0 and ratio == 1.0
