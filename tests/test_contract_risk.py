"""契约测试 — 风控门禁（docs/contracts/contract_risk.md）。

§2 参数锁定测试：改值必须先改契约，否则本文件失败。
§3 状态机：突变/查询分离纪律 + 边界。
§0 总则：fail-closed、无模式旁路的骨架级验证。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from config import settings
from engine.risk import gatekeeper as gk

P = settings.RISK_PARAMS


class TestRiskParamsLocked:
    """契约 §2 锁定表——逐键断言，数值来自旧库实码。"""

    def test_risk_params_locked(self):
        locked = {
            "max_daily_loss_pct": 12.0,
            "per_strategy_max_positions": 1,
            "floating_loss_warn_pct": 5.0,
            "floating_loss_block_pct": 10.0,
            "per_strategy_realized_loss_pct": 5.0,
            "per_strategy_loss_block_hours": 12,
            "per_strategy_realized_loss_amount": 30.0,
            "max_consecutive_losses": 3,
            "consecutive_loss_cooldown_hours": 4,
            "max_rapid_exits": 3,
            "rapid_exit_window_seconds": 300,
            "rapid_exit_cooldown_seconds": 7200,
            "profit_exit_cooldown_hours": 2,
            "min_hold_seconds": 30,
            "same_dir_float_loss_block": 0.5,
            "news_before_minutes": 30,
            "news_after_minutes": 120,
            "news_bias_adx_gate": 25,
            "news_bias_di_gap": 8,
            "position_gate_m30_lookback": 40,
            "position_gate_bottom": 0.10,
            "position_gate_top": 0.90,
            "di_gate_skip_threshold": 20,
            "rally_drop_lookback": 30,
            "rally_drop_threshold": 1.5,
            "rally_drop_adx_skip": 25,
        }
        for key, value in locked.items():
            assert P[key] == value, f"风控参数漂移: {key}={P[key]}≠{value}（先改契约再改值）"


def _state(magic=661402):
    return gk.StrategyRiskState(name="t", magic=magic)


class TestConsecutiveLoss:
    """契约 §3 + T-G7：突变/查询分离（旧库双调用重复计数回归）。"""

    def test_mutation_query_separation(self):
        state = _state()
        gk.register_trade_result(state, -10.0)
        gk.register_trade_result(state, -10.0)
        # 连续两次 check 不改变状态（旧库回归：check 被当 register 调用导致 +2）
        assert gk.check_consecutive_loss(state, 3) is False
        assert gk.check_consecutive_loss(state, 3) is False
        assert state.consecutive_losses == 2

    def test_three_losses_trigger(self):
        state = _state()
        for _ in range(3):
            gk.register_trade_result(state, -5.0)
        assert gk.check_consecutive_loss(state, P["max_consecutive_losses"]) is True

    def test_profit_resets_zero_pnl_neutral(self):
        state = _state()
        gk.register_trade_result(state, -5.0)
        gk.register_trade_result(state, -5.0)
        gk.register_trade_result(state, 0.0)      # 保本：不计不清
        assert state.consecutive_losses == 2
        gk.register_trade_result(state, 1.0)      # 盈利：清零
        assert state.consecutive_losses == 0


class TestRapidExit:
    """T-G8：窗口边界。"""

    def test_window_boundary(self):
        state = _state()
        now = 1_000_000.0
        for t in (now - 299, now - 250, now - 100):
            state.exit_timestamps.append(t)
        assert gk.check_rapid_exit(state, P["rapid_exit_window_seconds"], 3, now) is True
        state2 = _state()
        for t in (now - 301, now - 250, now - 100):   # 一条刚出窗
            state2.exit_timestamps.append(t)
        assert gk.check_rapid_exit(state2, P["rapid_exit_window_seconds"], 3, now) is False

    def test_prune_keeps_pure_query(self):
        state = _state()
        now = 1_000_000.0
        state.exit_timestamps.extend([now - 1000, now - 100])
        gk.prune_exit_window(state, P["rapid_exit_window_seconds"], now)
        assert len(state.exit_timestamps) == 1


class TestRealizedLoss:
    """T-G6a/G6b：阈值与边界（含 float 边缘）。"""

    def test_amount_threshold(self):
        state = _state()
        state.realized_pnl = -30.0    # ≤ -30 触发（旧库语义 realized_pnl <= -threshold）
        assert gk.check_realized_loss_amount(state, P["per_strategy_realized_loss_amount"]) is True
        state.realized_pnl = -29.99
        assert gk.check_realized_loss_amount(state, P["per_strategy_realized_loss_amount"]) is False

    def test_pct_threshold(self):
        state = _state()
        state.realized_pnl = -510.0
        assert gk.check_realized_loss_pct(state, 10_000.0, 5.0) is True
        assert gk.check_realized_loss_pct(state, 10_000.0, 5.2) is False
        assert gk.check_realized_loss_pct(state, 0, 5.0) is False   # balance<=0 不误触发


class TestCooldownExpiry:
    def test_consecutive_cooldown_expiry(self):
        state = _state()
        now = 1_000_000.0
        gk.mark_blocked(state, "consecutive_loss", now)
        assert gk.is_consecutive_loss_blocked(state, now + 4 * 3600 - 1) is True
        assert gk.is_consecutive_loss_blocked(state, now + 4 * 3600 + 1) is False

    def test_rapid_cooldown_expiry(self):
        state = _state()
        now = 1_000_000.0
        gk.mark_blocked(state, "rapid_exit", now)
        assert gk.is_rapid_exit_blocked(state, now + 7200 - 1) is True
        assert gk.is_rapid_exit_blocked(state, now + 7200 + 1) is False


class TestGateEvaluation:
    """有序评估 + fail-closed（D8）+ 无模式旁路（D2）。"""

    def _ctx(self, **kw):
        ctx = {"risk_state": _state(), "now": 1_000_000.0,
               "balance": 10_000.0, "n_open_positions": 0}
        ctx.update(kw)
        return ctx

    def test_all_pass(self, tmp_path, monkeypatch):
        # 急停文件不存在（指向 tmp，避免读到真实锁）
        monkeypatch.setattr(settings, "SAFETY_LOCK_PATH", str(tmp_path / "no_lock.txt"))
        # 未接线的门禁（G1/G2/G5/G12/G13/G14）在 M0 会抛错 → fail-closed 拦截，
        # 因此这里直接单测已接线门禁的组合行为：
        assert gk.g3_global_daily_loss(self._ctx(day_realized_pnl=-500.0)).blocked is False
        assert gk.g9_max_positions(self._ctx(n_open_positions=0)).blocked is False

    def test_g3_blocks_over_12pct(self):
        r = gk.g3_global_daily_loss(self._ctx(day_realized_pnl=-1_300.0))
        assert r.blocked and r.gate_id == "G3"

    def test_g9_blocks_at_limit(self):
        r = gk.g9_max_positions(self._ctx(n_open_positions=1))
        assert r.blocked and r.gate_id == "G9"

    def test_g10_same_dir_float_loss(self):
        r = gk.g10_same_dir_float_loss(self._ctx(same_dir_floating_pnl=-0.6))
        assert r.blocked and r.gate_id == "G10"
        r2 = gk.g10_same_dir_float_loss(self._ctx(same_dir_floating_pnl=-0.4))
        assert r2.blocked is False

    def test_g11_profit_cooldown(self):
        r = gk.g11_profit_exit_cooldown(self._ctx(profit_exit_cooldown_until=1_000_000.0 + 100))
        assert r.blocked and r.gate_id == "G11"

    def test_fail_closed_on_gate_error(self, tmp_path, monkeypatch):
        """门禁抛错 = 拦截（fail-closed）。注入一个抛错的门禁验证 evaluate 路径。"""
        monkeypatch.setattr(settings, "SAFETY_LOCK_PATH", str(tmp_path / "no_lock.txt"))

        def boom(_ctx):
            raise RuntimeError("注入故障")

        monkeypatch.setattr(gk, "GATES", [gk.GATES[0], boom, *gk.GATES[2:]])
        result = gk.evaluate(self._ctx())
        assert result.blocked is True
        assert result.gate_id == "gate_error"

    def test_g5_weekend_and_hours(self, monkeypatch):
        from datetime import datetime, timezone
        # 2026-10-03 = 周六 12:00 UTC → 休市
        sat = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc).timestamp()
        assert gk.g5_market_open({"now": sat}).blocked is True
        # 2026-10-04 = 周日 10:00 UTC（<21 点）→ 未开市
        sun_am = datetime(2026, 10, 4, 10, 0, tzinfo=timezone.utc).timestamp()
        assert gk.g5_market_open({"now": sun_am}).blocked is True
        # 周日 22:00 UTC → 开市
        sun_pm = datetime(2026, 10, 4, 22, 0, tzinfo=timezone.utc).timestamp()
        assert gk.g5_market_open({"now": sun_pm}).blocked is False
        # 周五 22:00 UTC（≥21 点）→ 已收市
        fri_night = datetime(2026, 10, 2, 22, 0, tzinfo=timezone.utc).timestamp()
        assert gk.g5_market_open({"now": fri_night}).blocked is True

    def test_g13_direction_filter(self, monkeypatch):
        monkeypatch.setattr(settings, "GLOBAL_DIRECTION_FILTER", "SELL_ONLY")
        r = gk.g13_direction_filter({"direction": "BUY"})
        assert r.blocked and r.gate_id == "G13"
        assert gk.g13_direction_filter({"direction": "SELL"}).blocked is False
        monkeypatch.setattr(settings, "GLOBAL_DIRECTION_FILTER", "BOTH")
        assert gk.g13_direction_filter({"direction": "BUY"}).blocked is False

    def test_g1_news_blackout_window(self):
        now = 1_800_000_000.0
        assert gk.g1_news_blackout({"now": now, "news_blackout_until": now + 600}).blocked
        assert not gk.g1_news_blackout({"now": now, "news_blackout_until": None}).blocked

    def test_g2_news_bias_block(self):
        ctx = {"direction": "BUY", "news_bias_block": "BUY"}
        assert gk.g2_news_bias(ctx).blocked
        assert not gk.g2_news_bias({"direction": "SELL", "news_bias_block": "BUY"}).blocked

    def test_g0_safety_lock_blocks(self, tmp_path, monkeypatch):
        lock = tmp_path / "safety_lock.txt"
        lock.write_text("locked", encoding="utf-8")
        monkeypatch.setattr(settings, "SAFETY_LOCK_PATH", str(lock))
        # G0 在表首：即使后面有 stub 也先被 G0 拦截
        result = gk.evaluate(self._ctx())
        assert result.blocked and result.gate_id == "G0"

    def test_gate_order_is_contract_order(self):
        """表顺序不可重排（契约 §1）：G0 第一、G11 之后不得插账户级门禁。"""
        names = [fn.__name__ for fn in gk.GATES]
        assert names[0] == "g0_safety_lock"
        assert names.index("g9_max_positions") < names.index("g10_same_dir_float_loss")
