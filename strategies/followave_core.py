"""followave_core.py — FollowAve 共享逻辑（M15/M30 薄壳的基类，扫描器排除）。

移植血统：旧库 `strategies/20260927_m30_followave_v2.py` v1.6（2026-09-27）逐行移植。
M2 准源纪律：**逻辑与参数零改动**——MT4 版仍是策略唯一准源，T2.6 重叠期对账达标
（≥95%）之前禁止改任何参数；改动必须先在 MT4 版发生并记 changelog，再 rebase 过来。

仅有的适配点（接口换血，非逻辑改动）：
1. BaseStrategy 新接口：__init__(magic, timeframe, data_provider)；信号方向用
   "BUY"/"SELL" 字符串（旧库 OrderType 枚举等价）。
2. 指标全部本地计算（engine/indicators.py，白名单键同名同义，Wilder/MT4 标准公式）。
3. _verify_entry 的 latest 形状 = 新缓存 {"candles": [...], "indicators": {...}}
   （旧库 DataFactory 缓存是扁平 dict，语义等价）。
4. 删除旧 _verify_entry 中对 Candle 输入不可达的死分支（`curr > prev` 对象比较），
   行为不变：K 线方向 = forming bar（candles[-1]）实体方向（INV-S1.2 价格/实体触发白名单）。
5. position 参数为属性式视图（ticket/order_type/open_price/volume），由引擎包装。
6. bb_mid_direction 值域随新指标引擎：UP/DOWN/NEUTRAL（旧库小写 up/down/flat），
   比较值相应适配；判定语义不变（SMA20 逐根斜率 ±0.02% 阈值）。
"""

from __future__ import annotations

import logging
from typing import Optional

from strategies.base import BaseStrategy

logger = logging.getLogger(__name__)


class FollowAveCore(BaseStrategy):
    """FollowAve — Stoch+BBI+BB 趋势跟踪（±DI 门禁 + 分批止盈 + Trailing Stop）"""

    # ── 参数（回测确定，移植自 v1.6，禁改）──
    DI_GATE = 2               # ±DI 差值门禁（v1.4：5→2）
    EXIT_CONFIRM_BARS = 3     # 趋势反转出场确认 K 线数
    TRAIL_ATR = 3.0           # trailing stop 倍数（M30=3.0 / M15=4.0，子类覆盖）

    # ── 分批止盈（v1.5）──
    PARTIAL_TP_ATR = 3.0      # 触及 入场价±3.0×ATR（入场冻结）时部分止盈
    PARTIAL_TP_FRAC = 0.50    # 部分止盈平仓比例
    PARTIAL_TP_MIN_LOTS = 1   # 持仓须 ≥ 1×最小手数才可拆分

    # ── Stoch（v1.3：入场 80/20；止盈阈值与入场分离）──
    STOCH_K_OVERBOUGHT = 80
    STOCH_K_OVERSOLD = 20
    STOCH_EXIT_OVERBOUGHT = 80
    STOCH_EXIT_OVERSOLD = 20

    # ── BB 触碰容差 ──
    BB_EXTREME_TOLERANCE = 3

    FIXED_LOTS = 0.01
    MAX_SLIPPAGE = 30

    def __init__(self, magic: int, timeframe: str, data_provider=None):
        super().__init__(magic, timeframe, data_provider)
        self._exit_state: dict = {}
        self._last_exit_detail: Optional[dict] = None   # 出场归因（journal 可读）

    # ─────────────── 辅助 ───────────────

    @staticmethod
    def _verify_entry(signal, tick_price, latest):
        """tick 级入场复核（G15）：价格须在 BBI/BB 中轨正确一侧，且 forming bar
        实体不逆方向（INV-S1.2 白名单内的价格/实体触发）。

        latest = 引擎完整缓存 {"candles": [...], "indicators": {...}}。
        """
        direction = signal.get("direction", "BUY")
        ind = latest.get("indicators", {}) if isinstance(latest, dict) else {}
        bbi = ind.get("bbi", 0)
        bb = ind.get("bb") or {}
        bb_mid = bb.get("mid", 0)
        candles = latest.get("candles", []) if isinstance(latest, dict) else []

        candle_trending_up = False
        candle_trending_down = False
        if len(candles) >= 2:
            curr = candles[-1]            # forming bar：仅实体方向触发
            if hasattr(curr, "close") and hasattr(curr, "open"):
                candle_trending_up = curr.close > curr.open
                candle_trending_down = curr.close < curr.open

        if direction == "BUY":
            if bbi and tick_price < bbi:
                logger.info(f"[FollowAve] 拒绝 BUY 入场：价格 {tick_price:.2f} < BBI {bbi:.2f}")
                return False
            if bb_mid and tick_price < bb_mid:
                logger.info(f"[FollowAve] 拒绝 BUY 入场：价格 {tick_price:.2f} < BB中轨 {bb_mid:.2f}")
                return False
            if candle_trending_down and not candle_trending_up:
                logger.info("[FollowAve] 拒绝 BUY 入场：K 线方向下跌")
                return False
        else:
            if bbi and tick_price > bbi:
                logger.info(f"[FollowAve] 拒绝 SELL 入场：价格 {tick_price:.2f} > BBI {bbi:.2f}")
                return False
            if bb_mid and tick_price > bb_mid:
                logger.info(f"[FollowAve] 拒绝 SELL 入场：价格 {tick_price:.2f} > BB中轨 {bb_mid:.2f}")
                return False
            if candle_trending_up and not candle_trending_down:
                logger.info("[FollowAve] 拒绝 SELL 入场：K 线方向上涨")
                return False
        return True

    def _get_bb(self) -> Optional[dict]:
        bb = self.get_indicator("bb")
        if isinstance(bb, dict) and "mid" in bb and bb.get("mid") is not None:
            return bb
        return None

    def _compute_stoch_completed(self) -> Optional[tuple]:
        """已完成 K 线的 Stoch(5,3,3)：(k_curr, d_curr, k_prev, d_prev)。

        curr = bar1（已闭合），prev = bar2。全部来自指标引擎
        （stoch_5_3_3 = 当前；stoch_k_prev/stoch_d_prev = 前一根），不自算。
        """
        st = self.get_indicator("stoch_5_3_3")
        if not st:
            return None
        k, d = st.get("k"), st.get("d")
        k_prev = self.get_indicator("stoch_k_prev")
        d_prev = self.get_indicator("stoch_d_prev")
        if None in (k, d, k_prev, d_prev):
            return None
        return float(k), float(d), float(k_prev), float(d_prev)

    # ─────────────── 入场逻辑 ───────────────

    def generate_signal(self) -> Optional[tuple]:
        candles = self.candles
        if len(candles) < 30:
            return None

        completed = candles[-2]           # bar1（已闭合）
        close = completed.close
        bbi = self.get_indicator("bbi")
        bb = self._get_bb()
        pdi = self.get_indicator("pdi")
        ndi = self.get_indicator("ndi")

        if any(v is None for v in [bbi, pdi, ndi, bb]):
            return None

        stoch_vals = self._compute_stoch_completed()
        if stoch_vals is None:
            return None
        stoch_k, stoch_d, stoch_k_prev, stoch_d_prev = stoch_vals

        bb_mid = bb.get("mid", 0)

        # ── ±DI 门禁（幅度）──
        di_diff = abs(pdi - ndi)
        if di_diff <= self.DI_GATE:
            return None

        # ── 多头：+DI > -DI, close>BBI, Stoch 金叉, K<80, close≥BB中轨 ──
        if pdi > ndi:
            golden_cross = (stoch_k > stoch_d and stoch_k_prev <= stoch_d_prev)
            if close > bbi and golden_cross and stoch_k < self.STOCH_K_OVERBOUGHT \
                    and close >= bb_mid:
                logger.info(f"[{self.name}] 信号做多: +DI={pdi:.1f} > -DI={ndi:.1f} "
                            f"BBI={bbi:.2f} StochK={stoch_k:.1f} close={close:.2f}")
                return ("BUY", 1, 0, ["FOLLOWAVE-LONG"], [], {
                    "bbi": round(bbi, 2), "stoch_k": round(stoch_k, 1),
                    "stoch_d": round(stoch_d, 1), "pdi": round(pdi, 1),
                    "ndi": round(ndi, 1), "bb_mid": round(bb_mid, 2)})

        # ── 空头：-DI > +DI, close<BBI, Stoch 死叉, K>20, close≤BB中轨 ──
        else:
            death_cross = (stoch_k < stoch_d and stoch_k_prev >= stoch_d_prev)
            if close < bbi and death_cross and stoch_k > self.STOCH_K_OVERSOLD \
                    and close <= bb_mid:
                logger.info(f"[{self.name}] 信号做空: -DI={ndi:.1f} > +DI={pdi:.1f} "
                            f"BBI={bbi:.2f} StochK={stoch_k:.1f} close={close:.2f}")
                return ("SELL", 0, 1, [], ["FOLLOWAVE-SHORT"], {
                    "bbi": round(bbi, 2), "stoch_k": round(stoch_k, 1),
                    "stoch_d": round(stoch_d, 1), "pdi": round(pdi, 1),
                    "ndi": round(ndi, 1), "bb_mid": round(bb_mid, 2)})

        return None

    # ─────────────── SL/TP ───────────────

    def get_dynamic_sl_tp(self, direction: str, entry_price: float,
                          atr_val: float = None) -> tuple:
        """宽止损兜底（BB 下轨止损更灵敏，但用 ATR 兜底）；无 TP（出场全托管）。"""
        if atr_val is None:
            atr_val = self.get_indicator("atr") or 10.0
        if atr_val <= 0:
            atr_val = 10.0
        stop_dist = max(atr_val * 3.0, 30.0)
        if direction == "BUY":
            return entry_price - stop_dist, 0
        return entry_price + stop_dist, 0

    # ─────────────── 出场逻辑 ───────────────

    def mark_extreme_entry(self, ticket):
        """引擎告知入场已成交，初始化出场状态（幂等）。

        partial_atr 在入场时冻结，供分批止盈算触发距离，避免 ATR 漂移。
        """
        self._last_exit_detail = None   # 新仓出生即清空，防上一笔归因串到本笔
        if str(ticket) in self._exit_state:
            return
        self._exit_state[str(ticket)] = {
            "exit_count": 0,
            "trail_peak": None,
            "last_bar_time": None,
            "touched_bb_extreme": False,
            "partial_done": False,
            "partial_atr": self.get_indicator("atr"),
        }

    def check_partial_exit(self, position, bid: float, ask: float) -> float:
        """分批止盈：bar1 收盘达 入场价 ± PARTIAL_TP_ATR×ATR(入场冻结) → 平 PARTIAL_TP_FRAC。

        触发判定用已闭合 K 线；每笔仅一次（partial_done 守卫）。
        """
        ticket = str(getattr(position, "ticket", id(position)))
        state = self._exit_state.get(ticket)
        if state is None or state.get("partial_done"):
            return 0.0

        candles = self.candles
        if not candles or len(candles) < 3:
            return 0.0
        close = candles[-2].close          # bar1，无重绘

        is_buy = (getattr(position, "order_type", "BUY") in ("OP_BUY", "BUY"))
        entry = getattr(position, "open_price", None)
        if not entry or entry <= 0:
            return 0.0

        # 手数不足以拆分 → 放弃分批，交由常规出场
        if float(getattr(position, "volume", 0) or 0) < 0.01 * self.PARTIAL_TP_MIN_LOTS:
            return 0.0

        atr = state.get("partial_atr")
        if atr is None or atr <= 0:
            atr = self.get_indicator("atr")   # 兜底补抓
            if atr is None or atr <= 0:
                return 0.0
            state["partial_atr"] = atr

        dist = self.PARTIAL_TP_ATR * atr
        reached = (close - entry) >= dist if is_buy else (entry - close) >= dist
        if not reached:
            return 0.0

        state["partial_done"] = True
        logger.info(f"[{self.name}] 分批止盈 {self.PARTIAL_TP_FRAC * 100:.0f}% "
                    f"{'LONG' if is_buy else 'SHORT'}: entry={entry:.2f} close={close:.2f} "
                    f"触发={self.PARTIAL_TP_ATR}×ATR({atr:.2f})={dist:.2f}")
        return self.PARTIAL_TP_FRAC

    def check_ema20_exit(self, position, bid: float, ask: float) -> bool:
        """出场四优先级（全部基于已完成 K 线）：
        ① 超买/超卖 Stoch 死叉/金叉止盈（须曾触 BB 极值）
        ② 趋势反转（close 破 BBI + bb_mid_direction 同向，连续 3 根）
        ③ BB 硬止损（收盘越过对面轨）
        ④ Trailing Stop（TRAIL_ATR × ATR 从极值回撤）
        """
        ticket = str(getattr(position, "ticket", id(position)))
        state = self._exit_state.get(ticket)
        if state is None:
            return False

        candles = self.candles
        if not candles or len(candles) < 3:
            return False

        completed = candles[-2]           # bar1
        completed_time = completed.time
        close = completed.close
        high = completed.high
        low = completed.low

        # 同一根已完成 K 线只处理一次
        if state.get("last_bar_time") == completed_time:
            return False

        is_buy = (getattr(position, "order_type", "BUY") in ("OP_BUY", "BUY"))

        bbi = self.get_indicator("bbi")
        bb = self._get_bb()
        if bbi is None or bb is None:
            return False

        bb_bot = bb.get("lower", 0)
        bb_top = bb.get("upper", 0)
        atr_val = self.get_indicator("atr") or 10.0

        # 趋势方向过滤：bb_mid_direction（SMA20 斜率 proxy；v1.3 A/B 结论，禁改）
        bbi_dir = self.get_indicator("bb_mid_direction") or "flat"

        # 标记已处理此 K 线
        state["last_bar_time"] = completed_time

        stoch_vals = self._compute_stoch_completed()

        if is_buy:
            if state["trail_peak"] is None or high > state["trail_peak"]:
                state["trail_peak"] = high

            if high >= bb_top - self.BB_EXTREME_TOLERANCE:
                state["touched_bb_extreme"] = True

            # ① 超买死叉止盈
            if state["touched_bb_extreme"] and stoch_vals is not None:
                k_curr, d_curr, k_prev, d_prev = stoch_vals
                if k_curr < d_curr and k_prev >= d_prev \
                        and k_curr > self.STOCH_EXIT_OVERBOUGHT:
                    self._last_exit_detail = {
                        "exit_type": "stoch_cross_tp", "side": "LONG",
                        "k": round(k_curr, 2), "d": round(d_curr, 2),
                        "partial": bool(state.get("partial_done"))}
                    return True

            # ② 趋势反转（连续 N 根确认）
            if close < bbi and bbi_dir == "DOWN":
                state["exit_count"] += 1
            else:
                state["exit_count"] = 0

            if state["exit_count"] >= self.EXIT_CONFIRM_BARS:
                self._last_exit_detail = {
                    "exit_type": "trend_reversal", "side": "LONG",
                    "close": round(close, 2), "bbi": round(bbi, 2),
                    "bars": state["exit_count"],
                    "partial": bool(state.get("partial_done"))}
                return True

            # ③ BB 硬止损
            if close < bb_bot:
                self._last_exit_detail = {
                    "exit_type": "bb_hard_stop", "side": "LONG",
                    "close": round(close, 2), "bb": round(bb_bot, 2),
                    "partial": bool(state.get("partial_done"))}
                return True

            # ④ Trailing stop
            if self.TRAIL_ATR > 0 and state["trail_peak"] is not None:
                trail_stop = state["trail_peak"] - self.TRAIL_ATR * atr_val
                if close < trail_stop:
                    self._last_exit_detail = {
                        "exit_type": "trail_stop", "side": "LONG",
                        "close": round(close, 2), "peak": round(state["trail_peak"], 2),
                        "atr": round(atr_val, 2), "mult": self.TRAIL_ATR,
                        "partial": bool(state.get("partial_done"))}
                    return True

        else:  # SHORT
            if state["trail_peak"] is None or low < state["trail_peak"]:
                state["trail_peak"] = low

            if low <= bb_bot + self.BB_EXTREME_TOLERANCE:
                state["touched_bb_extreme"] = True

            # ① 超卖金叉止盈
            if state["touched_bb_extreme"] and stoch_vals is not None:
                k_curr, d_curr, k_prev, d_prev = stoch_vals
                if k_curr > d_curr and k_prev <= d_prev \
                        and k_curr < self.STOCH_EXIT_OVERSOLD:
                    self._last_exit_detail = {
                        "exit_type": "stoch_cross_tp", "side": "SHORT",
                        "k": round(k_curr, 2), "d": round(d_curr, 2),
                        "partial": bool(state.get("partial_done"))}
                    return True

            # ② 趋势反转
            if close > bbi and bbi_dir == "UP":
                state["exit_count"] += 1
            else:
                state["exit_count"] = 0

            if state["exit_count"] >= self.EXIT_CONFIRM_BARS:
                self._last_exit_detail = {
                    "exit_type": "trend_reversal", "side": "SHORT",
                    "close": round(close, 2), "bbi": round(bbi, 2),
                    "bars": state["exit_count"],
                    "partial": bool(state.get("partial_done"))}
                return True

            # ③ BB 硬止损
            if close > bb_top:
                self._last_exit_detail = {
                    "exit_type": "bb_hard_stop", "side": "SHORT",
                    "close": round(close, 2), "bb": round(bb_top, 2),
                    "partial": bool(state.get("partial_done"))}
                return True

            # ④ Trailing stop
            if self.TRAIL_ATR > 0 and state["trail_peak"] is not None:
                trail_stop = state["trail_peak"] + self.TRAIL_ATR * atr_val
                if close > trail_stop:
                    self._last_exit_detail = {
                        "exit_type": "trail_stop", "side": "SHORT",
                        "close": round(close, 2), "peak": round(state["trail_peak"], 2),
                        "atr": round(atr_val, 2), "mult": self.TRAIL_ATR,
                        "partial": bool(state.get("partial_done"))}
                    return True

        return False
