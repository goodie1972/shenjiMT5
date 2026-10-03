"""strategies/base.py — 策略基类（契约一 docs/contracts/contract_strategy.md 的实现形状）。

形状继承自旧库实盘验证的 base.py v2，依赖改为注入式数据源：
- INV-S1 bar1 纪律：refresh_data 暴露的指标缓存顶层永远是 bar1（已闭合 K 线）值；
  forming bar（candles[-1]）只准做价格/实体触发。
- INV-S2 白名单：get_indicator 取未登记键直接抛错（旧库 kiss/goodma 静默 None 的教训）。
"""

from __future__ import annotations

import abc
import logging
from typing import Any, Callable, Optional

from config import settings

logger = logging.getLogger(__name__)

STRATEGY_BASE_VERSION = "v1"

# ── INV-S2 指标键白名单（冻结自旧库 _EA_CACHE_KEYS 56 键 + TA-only 派生键）──
INDICATOR_WHITELIST: frozenset[str] = frozenset({
    "rsi", "rsi_5", "rsi_10", "mfi", "bb", "bb_width",
    "ema_9", "ema_21", "ema_34", "ema_50", "ema_200",
    "sma_14", "sma_20", "sma_50",
    "atr", "atr_20", "adx", "pdi", "ndi",
    "macd", "stoch_5_3_3", "linear_reg_slope",
    "volume_sma_20", "close", "cci", "cci_direction", "wpr",
    "demarker", "bulls_power", "bears_power", "force_index",
    "obv", "momentum", "std_dev", "sar",
    "ao", "osma", "ac", "bwmfi", "ad",
    "env_upper", "env_lower",
    "rvi_main", "rvi_signal",
    "ichi_tenkan", "ichi_kijun", "ichi_senkou_a", "ichi_senkou_b",
    "alligator_jaw", "alligator_teeth", "alligator_lips",
    "gator_upper", "gator_lower",
    "fractal_upper", "fractal_lower",
    # TA-only 派生键（旧库同款；bb_mid 为 MT5 版新增，见 contract_strategy v1.1）
    "stoch_rsi", "stoch_k_prev", "stoch_d_prev",
    "candle_pattern_dir", "candle_pattern_name",
    "bbi", "bb_mid", "bb_mid_direction", "trend", "price_position",
    "mfi_direction", "rsi_dir_3bar",
})

OrderType = str  # "BUY" | "SELL"；None = 无信号


class Candle:
    """K 线。time = 开盘时刻 UTC 秒（契约 INV-S3）。"""

    __slots__ = ("time", "open", "high", "low", "close", "volume")

    def __init__(self, time: int, open: float, high: float, low: float,
                 close: float, volume: float = 0.0):
        self.time, self.open, self.high, self.low, self.close = time, open, high, low, close
        self.volume = volume


DataProvider = Callable[[str, int], dict]
"""数据源：data_provider(timeframe, count) -> {"candles": [Candle 升序],
"indicators": {key: bar1值}}。指标必须已是 bar1 值（INV-S1 由数据层保证）。"""


class BaseStrategy(abc.ABC):
    """策略基类。子类只实现 generate_signal 与（可选）退出钩子。"""

    name = "base"
    legacy_magics: list[int] = []

    def __init__(self, magic: int, timeframe: str,
                 data_provider: Optional[DataProvider] = None):
        self.magic = magic
        self.timeframe = timeframe
        self.symbol = settings.SYMBOL
        self.data_provider = data_provider
        self.candles: list[Candle] = []            # 升序；[-1]=bar0(forming)，[-2]=bar1
        self._cached_indicators: dict[str, Any] = {}   # 顶层 = bar1 值
        self._last_signal: Optional[dict] = None
        self._last_exit_detail: Optional[dict] = None

    @property
    def all_magics(self) -> set[int]:
        return {self.magic} | set(self.legacy_magics)

    # ── 取数 ────────────────────────────────────────────────
    def refresh_data(self, count: int = 200) -> None:
        """从注入数据源取 K 线与 bar1 指标。数据源未注入 → 明确报错。"""
        if self.data_provider is None:
            raise RuntimeError(f"[{self.name}] data_provider 未注入")
        data = self.data_provider(self.timeframe, count)
        self.candles = data.get("candles", [])
        self._cached_indicators = data.get("indicators", {})

    # ── 指标（INV-S2）───────────────────────────────────────
    def get_indicator(self, name: str):
        """读取 bar1 指标单值。未登记键直接抛错——静默 None 是旧库 23 天零成交的教训。"""
        if name not in INDICATOR_WHITELIST:
            raise KeyError(
                f"[{self.name}] 指标键 '{name}' 不在白名单（INV-S2）。"
                "新键必须走契约变更流程，禁止自算指标。")
        return self._cached_indicators.get(name)

    def get_indicator_series(self, name: str, n: int = 10) -> list:
        """指标历史序列（旧→新，末项 = 当前 bar1）。M1 由 indicator_snapshots 支撑。"""
        if name not in INDICATOR_WHITELIST:
            raise KeyError(f"[{self.name}] 指标键 '{name}' 不在白名单（INV-S2）")
        return []

    def get_close_prices(self) -> list[float]:
        return [c.close for c in self.candles]

    def bar1(self) -> Optional[Candle]:
        """已闭合 K 线（INV-S1 的唯一合法判定来源）。"""
        return self.candles[-2] if len(self.candles) >= 2 else None

    # ── 打分（S-1 六元组）───────────────────────────────────
    @abc.abstractmethod
    def generate_signal(self):
        """返回 tuple[Optional[OrderType], score_long, score_short,
        factors_long, factors_short, indicator_values(, confidence)]。"""

    # ── 引擎入口（子类不覆写）───────────────────────────────
    def on_tick(self) -> Optional[str]:
        self.refresh_data()
        if len(self.candles) < settings.MIN_CANDLES_FOR_SIGNAL:
            logger.warning("[%s] K 线不足: %d", self.name, len(self.candles))
            return None
        result = self.generate_signal()
        if result is None:
            return None                      # 无信号（契约 S-1 v1.2：None 合法）
        if not isinstance(result, tuple) or len(result) < 6:
            raise TypeError(f"[{self.name}] generate_signal 必须返回六元组或 None（契约 S-1）")
        if not isinstance(result, tuple) or len(result) < 6:
            raise TypeError(f"[{self.name}] generate_signal 必须返回六元组（契约 S-1）")
        signal = result[0]
        self._last_signal = {
            "signal": signal if signal else None,
            "score_long": result[1], "score_short": result[2],
            "factors_long": list(result[3]), "factors_short": list(result[4]),
            "indicator_values": result[5],
        }
        if len(result) > 6:
            self._last_signal["confidence"] = result[6]
        if signal not in (None, "BUY", "SELL"):
            raise ValueError(f"[{self.name}] 非法信号: {signal!r}（只允许 BUY/SELL/None）")
        return f"Signal: {signal}" if signal else None

    # ── 过滤（G12 宿主）─────────────────────────────────────
    def calc_gate_state(self, direction: str, price: float,
                        adx_data: Optional[dict]) -> dict:
        """K 线门禁（位置门禁/追高惩罚）。默认放行；子类按需覆写。"""
        return {"blocked": False, "reason": ""}

    # ── 退出钩子（引擎每 tick 调用；默认全不触发）───────────
    def check_ema20_exit(self, position: dict, bid: float, ask: float) -> bool:
        return False

    def check_partial_exit(self, position: dict, bid: float, ask: float) -> float:
        return 0.0

    def mark_extreme_entry(self, ticket: int) -> None:
        """成交回调：冻结入场时点状态（如入场 ATR）。"""

    def get_dynamic_sl_tp(self, direction: str, entry_price: float):
        """返回 (sl, tp)；(None, None) 时引擎兜底 2×ATR / 4×ATR。"""
        return None, None

    def get_adx_data(self) -> Optional[dict]:
        return None

    def _verify_entry(self, signal: dict, tick_price: float,
                      latest_cache: dict) -> bool:
        """可选静态复核钩子；forming bar 只准做价格/实体触发（INV-S1.2）。"""
        return True
