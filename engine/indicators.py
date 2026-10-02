"""engine/indicators.py — 本地指标引擎（T1.2，轨道1）。

契约定位：
- 白名单（strategies.base.INDICATOR_WHITELIST）不变；本引擎分两个实现层：
  * COMPUTED_KEYS — 已实现，bar1 值随缓存供给；
  * PENDING_KEYS  — 尚未实现。**策略请求 PENDING 键 = 报错**（fail-closed），
    绝不静默返回 None——旧库 kiss/goodma 因动态键静默 None 造成 23 天零成交。
- MT4 内置指标按 Wilder/MT4 标准公式实现（rsi/atr/adx 与旧库 F043 的 EA 直供值
  同源同义，供 M2 对齐）；派生键（trend/bbi/candle_pattern 等）的定义以本文件
  注释为准，是 MT5 版的新规范。

所有函数输入为已闭合 bar 的 DataFrame（time/open/high/low/close/volume，升序，
time=UTC 秒），输出 bar1（末根）值。禁止接触 forming bar（INV-S1）。
"""

from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

# ── 实现层注册表 ──────────────────────────────────────────────
COMPUTED_KEYS: set[str] = set()
PENDING_KEYS: set[str] = {
    # MT4 原生但暂未实现的 exotic 键：实现后移入 COMPUTED_KEYS 并补单测
    "demarker", "bulls_power", "bears_power", "force_index", "sar",
    "ao", "osma", "ac", "bwmfi", "ad",
    "env_upper", "env_lower", "rvi_main", "rvi_signal",
    "ichi_tenkan", "ichi_kijun", "ichi_senkou_a", "ichi_senkou_b",
    "alligator_jaw", "alligator_teeth", "alligator_lips",
    "gator_upper", "gator_lower", "fractal_upper", "fractal_lower",
}

_DISPATCH: dict[str, tuple[Callable, dict]] = {}


def _bind(keys: tuple[str, ...], fn: Callable, **params) -> None:
    for k in keys:
        COMPUTED_KEYS.add(k)
        _DISPATCH[k] = (fn, params)


def _sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _wilder(s: pd.Series, n: int) -> pd.Series:
    """Wilder 平滑（MT4 iRSI/iATR/iADX 同源）。"""
    return s.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()


# ── 均线 ─────────────────────────────────────────────────────

def ema(df: pd.DataFrame, key: str) -> float:
    return float(_ema(df["close"], int(key.split("_")[1])).iloc[-1])


def sma(df: pd.DataFrame, key: str) -> float:
    return float(_sma(df["close"], int(key.split("_")[1])).iloc[-1])


_bind(("ema_9", "ema_21", "ema_34", "ema_50", "ema_200"), ema)
_bind(("sma_14", "sma_20", "sma_50"), sma)


# ── 动能/超买超卖 ────────────────────────────────────────────

def _rsi_series(close: pd.Series, n: int) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0.0)
    down = (-delta).clip(lower=0.0)
    avg_up = _wilder(up, n)
    avg_down = _wilder(down, n)
    rs = avg_up / avg_down.replace(0.0, np.nan)
    out = 100.0 - 100.0 / (1.0 + rs)
    out = out.where(avg_down > 0, 100.0)     # 单边上涨（avg_down=0）→ 100
    out = out.where(avg_up > 0, 0.0)         # 单边下跌（avg_up=0）→ 0
    both_zero = (avg_up == 0) & (avg_down == 0)
    return out.mask(both_zero, 50.0)


def rsi(df: pd.DataFrame, key: str) -> float:
    n = {"rsi": 14, "rsi_5": 5, "rsi_10": 10}[key]
    return float(_rsi_series(df["close"], n).iloc[-1])


_bind(("rsi", "rsi_5", "rsi_10"), rsi)


def _mfi_series(df: pd.DataFrame, n: int = 14) -> pd.Series:
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    flow = tp * df["volume"]
    delta = tp.diff()
    pos = flow.where(delta > 0, 0.0).rolling(n).sum()
    neg = flow.where(delta < 0, 0.0).rolling(n).sum()
    return 100.0 - 100.0 / (1.0 + pos / neg.replace(0.0, np.nan))


def mfi(df: pd.DataFrame, key: str) -> float:
    return float(_mfi_series(df).iloc[-1])


_bind(("mfi",), mfi)


def mfi_direction(df: pd.DataFrame, key: str) -> str:
    s = _mfi_series(df).iloc[-3:]
    if s.isna().any():
        return "FLAT"
    a, b, c = s
    if a < b < c:
        return "UP"
    if a > b > c:
        return "DOWN"
    return "FLAT"


_bind(("mfi_direction",), mfi_direction)


def _cci_series(df: pd.DataFrame, n: int = 14) -> pd.Series:
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    sma_tp = tp.rolling(n).mean()
    mad = (tp - sma_tp).abs().rolling(n).mean()
    return (tp - sma_tp) / (0.015 * mad)


def cci(df: pd.DataFrame, key: str) -> float:
    return float(_cci_series(df).iloc[-1])


_bind(("cci",), cci)


def cci_direction(df: pd.DataFrame, key: str) -> str:
    s = _cci_series(df)
    a, b = s.iloc[-2], s.iloc[-1]
    if pd.isna(a) or pd.isna(b):
        return "FLAT"
    return "UP" if b > a else "DOWN"


_bind(("cci_direction",), cci_direction)


def wpr(df: pd.DataFrame, key: str, n: int = 14) -> float:
    hh = df["high"].rolling(n).max().iloc[-1]
    ll = df["low"].rolling(n).min().iloc[-1]
    rng = hh - ll
    if not rng:
        return -50.0
    return float((hh - df["close"].iloc[-1]) / rng * -100.0)


_bind(("wpr",), wpr)


def momentum(df: pd.DataFrame, key: str, n: int = 14) -> float:
    """MT4 口径：当前价 / n 根前价 × 100。"""
    if len(df) <= n:
        return float("nan")
    return float(df["close"].iloc[-1] / df["close"].iloc[-1 - n] * 100.0)


_bind(("momentum",), momentum)


def obv(df: pd.DataFrame, key: str) -> float:
    sign = np.sign(df["close"].diff().fillna(0.0))
    return float((sign * df["volume"]).cumsum().iloc[-1])


_bind(("obv",), obv)


def std_dev(df: pd.DataFrame, key: str, n: int = 20) -> float:
    return float(df["close"].rolling(n).std(ddof=0).iloc[-1])


_bind(("std_dev",), std_dev)


def linear_reg_slope(df: pd.DataFrame, key: str, n: int = 14) -> float:
    """末 14 根 close 线性回归斜率（每根 bar 的价格变化量）。"""
    if len(df) < n:
        return float("nan")
    y = df["close"].iloc[-n:].to_numpy(dtype=float)
    x = np.arange(n, dtype=float)
    return float(np.polyfit(x, y, 1)[0])


_bind(("linear_reg_slope",), linear_reg_slope)


# ── 波动/趋势强度 ────────────────────────────────────────────

def _tr(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    a = df["high"] - df["low"]
    b = (df["high"] - prev_close).abs()
    c = (df["low"] - prev_close).abs()
    return pd.concat([a, b, c], axis=1).max(axis=1)


def atr(df: pd.DataFrame, key: str) -> float:
    n = 14 if key == "atr" else 20
    return float(_wilder(_tr(df), n).iloc[-1])


_bind(("atr", "atr_20"), atr)


def _adx_frame(df: pd.DataFrame, n: int = 14) -> pd.DataFrame:
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
    tr_w = _wilder(_tr(df), n)
    pdi = 100.0 * _wilder(plus_dm, n) / tr_w.replace(0.0, np.nan)
    ndi = 100.0 * _wilder(minus_dm, n) / tr_w.replace(0.0, np.nan)
    dx = 100.0 * (pdi - ndi).abs() / (pdi + ndi).replace(0.0, np.nan)
    adx = _wilder(dx.replace([np.inf, -np.inf], np.nan), n)
    return pd.DataFrame({"pdi": pdi, "ndi": ndi, "adx": adx})


def adx_family(df: pd.DataFrame, key: str) -> float:
    val = _adx_frame(df)[key].iloc[-1]
    return float(val) if pd.notna(val) else float("nan")


_bind(("adx", "pdi", "ndi"), adx_family)


# ── 布林/布林相关派生 ────────────────────────────────────────

def _bb_series(df: pd.DataFrame, n: int = 20, k: float = 2.0):
    mid = _sma(df["close"], n)
    sd = df["close"].rolling(n).std(ddof=0)
    return mid, mid + k * sd, mid - k * sd


def bb_family(df: pd.DataFrame, key: str) -> float | dict | str:
    mid, upper, lower = _bb_series(df)
    m, u, l = mid.iloc[-1], upper.iloc[-1], lower.iloc[-1]
    if key == "bb":
        if pd.isna(m):
            return {"upper": None, "mid": None, "lower": None}
        return {"upper": float(u), "mid": float(m), "lower": float(l)}
    if key == "bb_width":
        if pd.isna(m) or m == 0:
            return float("nan")
        return float((u - l) / m * 100.0)
    if key == "bb_mid":
        return float(m) if pd.notna(m) else None
    if key == "bb_mid_direction":
        # SMA20 逐根斜率（|斜率| > 0.02% 视为方向；FollowAve 出场判定用）
        if len(mid.dropna()) < 2 or pd.isna(m):
            return "NEUTRAL"
        prev = mid.iloc[-2]
        if pd.isna(prev) or prev == 0:
            return "NEUTRAL"
        slope = (m - prev) / prev
        if slope > 0.0002:
            return "UP"
        if slope < -0.0002:
            return "DOWN"
        return "NEUTRAL"
    raise KeyError(key)


_bind(("bb", "bb_width", "bb_mid", "bb_mid_direction"), bb_family)


def bbi(df: pd.DataFrame, key: str) -> float:
    """多空指标 BBI = (SMA3+SMA6+SMA12+SMA24)/4。"""
    return float(sum(_sma(df["close"], n).iloc[-1] for n in (3, 6, 12, 24)) / 4.0)


_bind(("bbi",), bbi)


def trend(df: pd.DataFrame, key: str) -> str:
    """多层均线排列：ema9>ema21>ema50 = UP，反向 = DOWN，否则 SIDE。"""
    e9 = _ema(df["close"], 9).iloc[-1]
    e21 = _ema(df["close"], 21).iloc[-1]
    e50 = _ema(df["close"], 50).iloc[-1]
    if any(pd.isna(v) for v in (e9, e21, e50)):
        return "SIDE"
    if e9 > e21 > e50:
        return "UP"
    if e9 < e21 < e50:
        return "DOWN"
    return "SIDE"


_bind(("trend",), trend)


def price_position(df: pd.DataFrame, key: str, n: int = 40) -> float:
    """G12 位置门禁同口径：close 在末 40 根 [低,高] 区间的分位（0~1）。"""
    hh = df["high"].rolling(n).max().iloc[-1]
    ll = df["low"].rolling(n).min().iloc[-1]
    if pd.isna(hh) or hh == ll:
        return 0.5
    return float((df["close"].iloc[-1] - ll) / (hh - ll))


_bind(("price_position",), price_position)


# ── Stoch / MACD ─────────────────────────────────────────────

def _stoch_frame(df: pd.DataFrame, k_n=5, slow=3, d_n=3) -> pd.DataFrame:
    """MT4 iStochastic(5,3,3)：K=慢化快K（5 根 slowed 3），D=K 的 3 根 SMA。"""
    hh = df["high"].rolling(k_n).max()
    ll = df["low"].rolling(k_n).min()
    fast_k = 100.0 * (df["close"] - ll) / (hh - ll).replace(0.0, np.nan)
    k = fast_k.rolling(slow).mean()
    d = k.rolling(d_n).mean()
    return pd.DataFrame({"k": k, "d": d})


def stoch(df: pd.DataFrame, key: str):
    f = _stoch_frame(df)
    if key == "stoch_5_3_3":
        k, d = f["k"].iloc[-1], f["d"].iloc[-1]
        return {"k": float(k) if pd.notna(k) else None,
                "d": float(d) if pd.notna(d) else None}
    val = f["k" if key == "stoch_k_prev" else "d"].iloc[-2]
    return float(val) if pd.notna(val) else None


_bind(("stoch_5_3_3", "stoch_k_prev", "stoch_d_prev"), stoch)


def stoch_rsi(df: pd.DataFrame, key: str, n: int = 14, k_n=5, d_n=3) -> float:
    r = _rsi_series(df["close"], n)
    hi = r.rolling(k_n).max()
    lo = r.rolling(k_n).min()
    k = 100.0 * (r - lo) / (hi - lo).replace(0.0, np.nan)
    return float(k.rolling(d_n).mean().iloc[-1])


_bind(("stoch_rsi",), stoch_rsi)


def macd(df: pd.DataFrame, key: str) -> dict:
    line = _ema(df["close"], 12) - _ema(df["close"], 26)
    signal = _ema(line, 9)
    return {"macd": float(line.iloc[-1]), "signal": float(signal.iloc[-1]),
            "hist": float((line - signal).iloc[-1])}


_bind(("macd",), macd)


def rsi_dir_3bar(df: pd.DataFrame, key: str) -> str:
    s = _rsi_series(df["close"], 14).iloc[-3:]
    if s.isna().any():
        return "FLAT"
    a, b, c = s
    if a < b < c:
        return "UP"
    if a > b > c:
        return "DOWN"
    return "FLAT"


_bind(("rsi_dir_3bar",), rsi_dir_3bar)


# ── 蜡烛形态（简单版，供 G12/展示）─────────────────────────

def candle_pattern(df: pd.DataFrame, key: str) -> int | str:
    """body 占全幅 >10% 定方向：dir ∈ 1/-1/0，name ∈ bull/bear/doji。"""
    o, c = df["open"].iloc[-1], df["close"].iloc[-1]
    h, l = df["high"].iloc[-1], df["low"].iloc[-1]
    body = c - o
    rng = (h - l) or 1e-9
    if key == "candle_pattern_dir":
        return 1 if body > 0.1 * rng else (-1 if body < -0.1 * rng else 0)
    return "bull" if body > 0.1 * rng else ("bear" if body < -0.1 * rng else "doji")


_bind(("candle_pattern_dir", "candle_pattern_name"), candle_pattern)


def volume_sma_20(df: pd.DataFrame, key: str) -> float:
    return float(_sma(df["volume"].astype(float), 20).iloc[-1])


_bind(("volume_sma_20",), volume_sma_20)


def close(df: pd.DataFrame, key: str) -> float:
    return float(df["close"].iloc[-1])


_bind(("close",), close)


# ── 求值入口 ─────────────────────────────────────────────────

def missing_for(required: set[str]) -> set[str]:
    """启动期检查：所需键里的 PENDING 集——非空则拒绝启动该策略（fail-closed）。"""
    return {k for k in required if k in PENDING_KEYS}


def compute_bar1(df: pd.DataFrame, keys: set[str] | None = None) -> dict:
    """计算全部（或指定）已实现键的 bar1 值。df = 已闭合 bar（升序）。

    NaN 统一转 None（JSON 可序列化）。请求 PENDING 键 → KeyError（fail-closed）。
    """
    keys = keys if keys is not None else set(COMPUTED_KEYS)
    pending = {k for k in keys if k in PENDING_KEYS}
    if pending:
        raise KeyError(f"指标键尚未实现（PENDING）: {sorted(pending)}")
    from strategies.base import INDICATOR_WHITELIST
    out: dict = {}
    for k in sorted(keys):
        if k not in _DISPATCH:
            if k not in INDICATOR_WHITELIST:
                raise KeyError(f"指标键 '{k}' 不在白名单")
            continue
        fn, params = _DISPATCH[k]
        try:
            val = fn(df, k, **params)
        except Exception:
            val = float("nan")
        if isinstance(val, float) and np.isnan(val):
            val = None
        elif isinstance(val, dict):
            val = {kk: (None if isinstance(vv, float) and np.isnan(vv) else vv)
                   for kk, vv in val.items()}
        out[k] = val
    return out
