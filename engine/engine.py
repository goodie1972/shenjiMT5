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
from engine import data_factory, reconcile as reconcile_mod
from engine.athlete import Athlete
from engine.journal import TradeJournal
from engine.risk import gatekeeper as gk

logger = logging.getLogger(__name__)

RECONCILE_INTERVAL_SEC = 6 * 3600


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
        self.athlete = Athlete(client, TradeJournal(), db_path=db_path, mode=mode)
        self._last_reconcile = 0.0
        self._stop = False

    # ── 生命周期 ─────────────────────────────────────────────
    def start(self) -> None:
        db.init_db(self.db_path)             # 幂等：建表 + 轻量迁移
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
        self._load_risk_states()
        self._run_reconcile()
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
                if settings.utc_now() - self._last_reconcile > RECONCILE_INTERVAL_SEC:
                    self._run_reconcile()
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
        """一个轮询周期：bar 闭合刷新 → 策略扫描 → 门禁 → Athlete → 出场管理。"""
        stats: dict = {"refreshed": [], "signals": 0, "blocked": 0, "passed": 0,
                       "opened": 0, "closed": 0}
        for tf in sorted({c["timeframe"] for c in self.pool.values()}):
            if self._bar_advanced(tf):
                self.refresh_tf(tf)
                stats["refreshed"].append(tf)
        if stats["refreshed"]:
            affected = [s for s in self.strategies if s.timeframe in stats["refreshed"]]
            futures = [self.executor.submit(self._process_strategy, s) for s in affected]
            for f in futures:
                f.result(timeout=60)
        stats["opened"] = len(self.athlete.verify_tick(self.caches))
        stats["closed"] = self._manage_exits()
        return stats

    def force_tick(self) -> dict:
        """测试辅助：无视桶边界强制刷新 + 全策略扫描（仅本 tick，不影响判定纪律）。"""
        for tf in self.caches:
            self.refresh_tf(tf)
        stats = {"refreshed": list(self.caches), "signals": 0, "blocked": 0,
                 "passed": 0, "opened": 0, "closed": 0}
        futures = [self.executor.submit(self._process_strategy, s) for s in self.strategies]
        for f in futures:
            f.result(timeout=60)
        stats["opened"] = len(self.athlete.verify_tick(self.caches))
        stats["closed"] = self._manage_exits()
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
            ticket = self.athlete.submit(strategy, signal_id, direction, sig)
            if ticket:
                logger.info("[engine] #%d 放行 → Athlete（G15 复核）", signal_id)

    # ── 轨道3：出场管理 + journal + 风控状态突变 ────────────
    def _manage_exits(self) -> int:
        if not self.athlete.open_entries:
            return 0
        positions = self.client.positions_open(settings.SYMBOL)
        live = {p["ticket"]: p for p in positions}
        tick = self.client.get_tick(settings.SYMBOL)
        closed = 0
        for ticket_id, entry in list(self.athlete.open_entries.items()):
            p = live.get(ticket_id)
            if p is None:
                # 仓位已不在（SL/TP 触发或手动平）→ journal 补记，真值待对账覆盖
                self._on_position_gone(entry)
                continue
            strat = entry.strategy
            if strat is None:
                continue
            if strat.check_ema20_exit(p, tick["bid"], tick["ask"]):
                if self._close(entry, p, 1.0, "strategy_exit", tick):
                    closed += 1
                continue
            frac = strat.check_partial_exit(p, tick["bid"], tick["ask"])
            if frac and frac > 0:
                self._close(entry, p, frac, "partial_exit", tick)
        return closed

    def _close(self, entry, position, frac: float, reason: str, tick) -> bool:
        spec = self.client.symbol_spec(settings.SYMBOL)
        if frac >= 1.0:
            volume = position["volume"]
        else:
            volume = round(position["volume"] * frac / spec["volume_step"]) * spec["volume_step"]
            if volume < spec["volume_min"] or position["volume"] - volume < spec["volume_min"]:
                logger.info("[athlete] %s 部分平仓量不足最小手，跳过（旧库纪律）",
                            entry.position_ticket)
                return False
        try:
            result = self.client.close_position(
                settings.SYMBOL, entry.position_ticket, entry.direction,
                volume, magic=entry.magic)
        except Exception:
            logger.exception("[athlete] 平仓失败 ticket=%s（下 tick 重试）",
                             entry.position_ticket)
            return False
        exit_price = result["price"]
        sign = 1.0 if entry.direction == "BUY" else -1.0
        pnl_est = None
        if entry.entry_price and spec["trade_tick_size"]:
            ticks = (exit_price - entry.entry_price) * sign / spec["trade_tick_size"]
            pnl_est = round(ticks * spec["trade_tick_value"] * volume, 2)
        now = int(settings.utc_now())
        hold = now - entry.open_ts
        record = {"position_ticket": entry.position_ticket,
                  "strategy": entry.strategy_name, "magic": entry.magic,
                  "direction": entry.direction, "volume": volume,
                  "entry_price": entry.entry_price, "exit_price": exit_price,
                  "sl": entry.sl, "tp": entry.tp, "pnl": pnl_est,
                  "pnl_source": "local_est", "open_ts": entry.open_ts,
                  "close_ts": now,
                  "hold_seconds": hold,
                  "exit_reason": reason, "mode": entry.mode, "source": "engine"}
        self.athlete.journal.append(record, db_path=self.db_path)
        if frac >= 1.0 or volume >= position["volume"]:
            self.athlete.open_entries.pop(entry.position_ticket, None)
        self._register_exit_result(entry, pnl_est, hold_seconds=hold)
        logger.info("[athlete] CLOSE %s %s vol=%.2f @ %.2f reason=%s pnl_est=%s",
                    entry.position_ticket, entry.direction, volume, exit_price,
                    reason, pnl_est)
        return True

    def _on_position_gone(self, entry) -> None:
        """在管仓位被 broker 侧平掉（SL/TP/手动）：journal 补记，pnl 标 None 待对账。"""
        self.athlete.open_entries.pop(entry.position_ticket, None)
        now = int(settings.utc_now())
        self.athlete.journal.append(
            {"position_ticket": entry.position_ticket, "strategy": entry.strategy_name,
             "magic": entry.magic, "direction": entry.direction,
             "volume": entry.volume, "entry_price": entry.entry_price,
             "exit_price": None, "sl": entry.sl, "tp": entry.tp, "pnl": None,
             "pnl_source": None, "open_ts": entry.open_ts, "close_ts": now,
             "hold_seconds": now - entry.open_ts, "exit_reason": "mt5_history",
             "mode": entry.mode, "source": "engine_gone"},
            db_path=self.db_path)
        self._register_exit_result(entry, None, hold_seconds=now - entry.open_ts)
        logger.info("[athlete] 仓位 %s 已被 broker 侧平掉（journal 补记，待对账）",
                    entry.position_ticket)

    def _register_exit_result(self, entry, pnl_est: Optional[float],
                              hold_seconds: Optional[int] = None) -> None:
        """风控状态突变：连亏计数、急速出场窗口、盈利平仓同向冷却、G0b 自动锁。"""
        state = self.risk_states.setdefault(
            entry.magic, gk.StrategyRiskState(name=entry.strategy_name, magic=entry.magic))
        pnl = pnl_est if pnl_est is not None else 0.0
        gk.register_trade_result(state, pnl)      # pnl None 按 0（不计数不清零）
        gk.record_exit(state, settings.utc_now())
        if pnl_est is not None and pnl_est > 0:
            self.profit_cooldown.setdefault(entry.magic, {})[entry.direction] = \
                settings.utc_now() + settings.RISK_PARAMS["profit_exit_cooldown_hours"] * 3600
        self._fast_close_auto_lock(entry, pnl_est, hold_seconds)
        self._save_risk_state(state)

    def _fast_close_auto_lock(self, entry, pnl_est: Optional[float],
                              hold_seconds: Optional[int]) -> None:
        """G0b：持仓 < min_hold_seconds 且亏损平仓 → 疑似异常，自动落安全锁。

        锁 = safety_lock 文件（G0 全局停开新仓），只能人工删除解锁。
        """
        import os
        min_hold = settings.RISK_PARAMS["min_hold_seconds"]
        if hold_seconds is None or pnl_est is None:
            return
        if hold_seconds < min_hold and pnl_est < 0:
            lock = settings.SAFETY_LOCK_PATH
            if not os.path.exists(lock):
                os.makedirs(os.path.dirname(lock), exist_ok=True)
                with open(lock, "w", encoding="utf-8") as f:
                    f.write(f"auto: suspected fast close magic={entry.magic} "
                            f"hold={hold_seconds}s pnl={pnl_est} "
                            f"at {int(settings.utc_now())}\n")
            logger.critical("[G0b] ⚠️ 疑似快速平仓（hold=%ss <%ss, pnl=%s）→ 已自动落锁 %s，"
                            "人工确认后删除该文件解锁", hold_seconds, min_hold, pnl_est, lock)

    # ── 风控状态持久化（T1.4 余项）─────────────────────────
    def _save_risk_state(self, state: gk.StrategyRiskState) -> None:
        import json
        data = {k: (list(v) if k == "exit_timestamps" else v)
                for k, v in state.__dict__.items()}
        conn = db.connect(self.db_path)
        try:
            conn.execute(
                "INSERT OR REPLACE INTO risk_states (magic, state_json, updated_ts)"
                " VALUES (?,?,?)",
                (state.magic, json.dumps(data), int(settings.utc_now())))
            conn.commit()
        finally:
            conn.close()

    def _load_risk_states(self) -> None:
        import json
        try:
            ro = db.readonly_connect(self.db_path)
            rows = ro.execute("SELECT magic, state_json FROM risk_states").fetchall()
            ro.close()
        except Exception:
            return
        for magic, state_json in rows:
            data = json.loads(state_json)
            state = gk.StrategyRiskState(
                name=data.get("name", f"magic:{magic}"), magic=int(magic),
                realized_pnl=data.get("realized_pnl", 0.0),
                consecutive_losses=data.get("consecutive_losses", 0),
                realized_loss_blocked=data.get("realized_loss_blocked", False),
                realized_loss_blocked_at=data.get("realized_loss_blocked_at", 0.0),
                realized_loss_amount_blocked=data.get("realized_loss_amount_blocked", False),
                realized_loss_amount_blocked_at=data.get("realized_loss_amount_blocked_at", 0.0),
                consecutive_loss_blocked=data.get("consecutive_loss_blocked", False),
                consecutive_loss_blocked_at=data.get("consecutive_loss_blocked_at", 0.0),
                rapid_exit_blocked=data.get("rapid_exit_blocked", False),
                rapid_exit_blocked_at=data.get("rapid_exit_blocked_at", 0.0))
            state.exit_timestamps.clear()
            state.exit_timestamps.extend(data.get("exit_timestamps", []))
            self.risk_states[int(magic)] = state
        if rows:
            logger.info("[engine] risk_states 恢复: %s 个策略", len(rows))

    def _run_reconcile(self) -> None:
        try:
            reconcile_mod.reconcile(self.client, db_path=self.db_path)
            self._last_reconcile = settings.utc_now()
        except Exception:
            logger.exception("[engine] 对账失败（下个周期重试）")

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
