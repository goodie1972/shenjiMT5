"""engine/engine.py — 三轨主循环（T1.1）。

轨道1 数据：bar 闭合检测 → pull_timeframe → build_cache（指标 + 快照）
轨道2 策略：线程池并发 on_tick（六元组信号）
轨道3 执行：GateKeeper G0~G14 有序评估 → 信号入库（pending/voided）。
          G15/Athlete 下单出场为 T1.3（本文件预留 execute 钩子）。

纪律：
- 全模式无门禁旁路（D2）：evaluate 结果只决定放行/拦截，永不跳过。
- fail-closed：策略线程抛错 = 本 tick 该策略跳过并告警，不中断循环。
- 时间一律 UTC（INV-S3）；桶偏移启动期从库内数据众数探测（contract_data §4）。
"""

from __future__ import annotations

import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

from config import settings
from config.settings import TF_SECONDS
from data import database as db
from engine import data_factory
from engine.risk import gatekeeper as gk

logger = logging.getLogger(__name__)


class Engine:
    def __init__(self, client, pool: dict[str, dict], mode: str = "demo",
                 poll_seconds: float = 1.0, db_path: str = settings.DB_PATH,
                 news_provider: Optional[Callable] = None,
                 bias_provider: Optional[Callable] = None):
        """pool: {name: {magic, timeframe}}（magic=0 视为禁用）。

        news_provider: callable(now)->黑屏窗口终点 UTC 秒或 None（G1 数据源）。
        bias_provider: callable()->封锁方向 'BUY'/'SELL'/None（G2 数据源）。
        """
        self.client = client
        self.pool = {n: c for n, c in pool.items() if c.get("magic", 0) != 0}
        self.mode = mode
        self.poll_seconds = poll_seconds
        self.db_path = db_path
        self.news_provider = news_provider
        self.bias_provider = bias_provider
        self.caches: dict[str, dict] = {}
        self.tf_offsets: dict[str, int] = {}
        self._last_bucket: dict[str, int] = {}
        self.risk_states: dict[int, gk.StrategyRiskState] = {}
        self.profit_cooldown: dict[int, dict[str, float]] = {}   # magic → dir → until
        self.strategies: list = []
        self.executor = ThreadPoolExecutor(max_workers=settings.STRATEGY_WORKERS)
        self._stop = False

    # ── 生命周期 ─────────────────────────────────────────────
    def start(self) -> None:
        self.client.connect()
        info = self.client.account_summary()
        logger.info("[engine] mode=%s login=%s server=%s balance=%.2f margin_mode=%s",
                    self.mode, info["login"], info["server"], info["balance"],
                    info["margin_mode_name"])
        if info["margin_mode"] != 2:
            logger.warning("[engine] ⚠️ 非对冲账户：v1 门禁按并发=1 设计，放开并发前必须"
                           "先定义 netting 语义（contract_strategy §7.2）")
        for tf in sorted({c["timeframe"] for c in self.pool.values()}):
            self.tf_offsets[tf] = self._detect_offset(tf)
            data_factory.pull_timeframe(self.client, tf, 300, self.db_path)
            self.caches[tf] = data_factory.build_cache(
                self.client, tf, settings.INDICATOR_LOOKBACK, self.db_path)
        self.strategies = self._create_strategies()
        for s in self.strategies:
            self.risk_states.setdefault(
                s.magic, gk.StrategyRiskState(name=s.name, magic=s.magic))
        logger.info("[engine] started: strategies=%s tfs=%s offsets=%s",
                    [s.name for s in self.strategies], sorted(self.caches),
                    self.tf_offsets)

    def stop(self) -> None:
        self._stop = True
        self.executor.shutdown(wait=True)

    def run_forever(self) -> None:
        self.start()
        while not self._stop:
            try:
                self.client.maybe_recalibrate()
                self.tick()
            except Exception:
                logger.exception("[engine] tick 异常（fail-safe：下个 tick 继续）")
            self._sleep(self.poll_seconds)

    def _sleep(self, seconds: float) -> None:
        import time
        end = time.time() + seconds
        while time.time() < end and not self._stop:
            time.sleep(min(0.2, end - time.time()))

    # ── 轨道1：数据 ──────────────────────────────────────────
    def _detect_offset(self, tf: str) -> int:
        rows = db.get_candles(tf, limit=500, db_path=self.db_path, order="DESC")
        if len(rows) < 10:
            return 0
        step = TF_SECONDS[tf]
        counts = Counter(int(r["timestamp"]) % step for r in rows)
        offset, n = counts.most_common(1)[0]
        if n / len(rows) < 0.95:
            logger.warning("[engine] %s 桶偏移一致率 %.1f%% <95%%，重探", tf, n / len(rows) * 100)
        return int(offset)

    def _bar_advanced(self, tf: str) -> bool:
        offset = self.tf_offsets.get(tf, 0)
        bucket = (int(settings.utc_now()) - offset) // TF_SECONDS[tf]
        last = self._last_bucket.get(tf)
        self._last_bucket[tf] = bucket
        return last is not None and bucket != last

    def refresh_tf(self, tf: str) -> None:
        data_factory.pull_timeframe(self.client, tf, 300, self.db_path)
        self.caches[tf] = data_factory.build_cache(
            self.client, tf, settings.INDICATOR_LOOKBACK, self.db_path)

    def tick(self) -> dict:
        """一个轮询周期：bar 闭合刷新 → 策略扫描 → 门禁 → 信号入库。"""
        stats: dict = {"refreshed": [], "signals": 0, "blocked": 0, "passed": 0}
        for tf in sorted({c["timeframe"] for c in self.pool.values()}):
            if self._bar_advanced(tf):
                self.refresh_tf(tf)
                stats["refreshed"].append(tf)
        if stats["refreshed"]:
            affected = [s for s in self.strategies if s.timeframe in stats["refreshed"]]
            futures = [self.executor.submit(self._process_strategy, s) for s in affected]
            for f in futures:
                f.result(timeout=60)
        return stats

    def force_tick(self) -> dict:
        """测试辅助：无视桶边界强制刷新 + 全策略扫描（仅本 tick，不影响判定纪律）。"""
        for tf in self.caches:
            self.refresh_tf(tf)
        stats = {"refreshed": list(self.caches), "signals": 0, "blocked": 0, "passed": 0}
        futures = [self.executor.submit(self._process_strategy, s) for s in self.strategies]
        for f in futures:
            f.result(timeout=60)
        return stats

    def _provide(self, tf: str, count: int) -> dict:
        cache = self.caches.get(tf)
        return cache or {"candles": [], "indicators": {}}

    # ── 轨道2+3：策略 → 门禁 → 信号 ─────────────────────────
    def _create_strategies(self) -> list:
        from strategies import scanner
        return scanner.create_strategies(self.pool, data_provider=self._provide)

    def _process_strategy(self, strategy) -> None:
        try:
            op = strategy.on_tick()
            if not op:
                return
            sig = strategy._last_signal or {}
            direction = sig.get("signal")
            if direction not in ("BUY", "SELL"):
                return
            self._handle_signal(strategy, direction, sig)
        except Exception:
            logger.exception("[engine] 策略 %s 处理异常（fail-safe 跳过）", strategy.name)

    def _handle_signal(self, strategy, direction: str, sig: dict) -> None:
        import json

        state = self.risk_states.setdefault(
            strategy.magic, gk.StrategyRiskState(name=strategy.name, magic=strategy.magic))
        positions = self.client.positions_open(settings.SYMBOL)
        mine = [p for p in positions if p["magic"] in strategy.all_magics]
        same_dir = [p for p in mine if p["type"] == direction]
        balance = self.client.account_summary()["balance"]

        bar1 = self.caches[strategy.timeframe]["candles"][-2]
        gate12 = strategy.calc_gate_state(direction, bar1.close, strategy.get_adx_data())

        blackout_until = None
        if self.news_provider and settings.NEWS_CALENDAR_PROVIDER:
            try:
                blackout_until = self.news_provider(settings.utc_now())
            except Exception:
                logger.exception("[engine] news_provider 异常（G1 放行并告警）")

        ctx = {
            "now": settings.utc_now(),
            "balance": balance,
            "day_realized_pnl": self._day_realized_pnl(),
            "strategy_floating_pnl": sum(p["profit"] for p in mine),
            "risk_state": state,
            "n_open_positions": len(mine),
            "max_positions": settings.RISK_PARAMS["per_strategy_max_positions"],
            "same_dir_floating_pnl": sum(p["profit"] for p in same_dir),
            "profit_exit_cooldown_until": self.profit_cooldown.get(
                strategy.magic, {}).get(direction),
            "direction": direction,
            "strategy_gate": gate12,
            "news_blackout_until": blackout_until,
            "news_bias_block": self._news_bias_block(),
            "mtf_block": None,
        }
        signal_id = db.insert_signal(
            strategy=strategy.name, magic=strategy.magic, timeframe=strategy.timeframe,
            direction=direction, score_long=int(sig.get("score_long") or 0),
            score_short=int(sig.get("score_short") or 0),
            factors_long=json.dumps(sig.get("factors_long", []), ensure_ascii=False),
            factors_short=json.dumps(sig.get("factors_short", []), ensure_ascii=False),
            indicator_values=json.dumps(sig.get("indicator_values", {}),
                                        ensure_ascii=False, default=str),
            confidence=sig.get("confidence"), db_path=self.db_path)
        logger.info("[engine] #%d %s %s %s | factors=%s", signal_id, strategy.name,
                    strategy.timeframe, direction, sig.get("factors_long") or sig.get("factors_short"))

        result = gk.evaluate(ctx)
        if result.blocked:
            db.update_signal_status(signal_id, "voided",
                                    exit_reason=f"{result.gate_id}:{result.reason}",
                                    db_path=self.db_path)
            logger.info("[engine] #%d 拦截 %s %s", signal_id, result.gate_id, result.reason)
        else:
            logger.info("[engine] #%d 全门禁放行 → Athlete（T1.3 接管下单）", signal_id)

    def _news_bias_block(self) -> Optional[str]:
        if not settings.NEWS_BIAS_BLOCK_ENABLED or not self.bias_provider:
            return None
        try:
            return self.bias_provider()
        except Exception:
            logger.exception("[engine] bias_provider 异常")
            return None

    def _day_realized_pnl(self) -> float:
        midnight = int(settings.utc_now()) // 86400 * 86400
        try:
            ro = db.readonly_connect(self.db_path)
            try:
                row = ro.execute("SELECT COALESCE(SUM(pnl),0) FROM trades"
                                 " WHERE close_ts >= ?", (midnight,)).fetchone()
                return float(row[0])
            finally:
                ro.close()
        except Exception:
            logger.exception("[engine] 日内盈亏查询失败（fail-closed 记 0 并告警）")
            return 0.0
