"""engine/risk/gatekeeper.py — 风控门禁唯一执行点。

契约依据：docs/contracts/contract_risk.md。
- 有序门禁表 G0~G15，首个 blocked 即拦截；fail-closed：门禁抛错 = blocked。
- 无模式旁路（D2）：实盘/demo/模拟器走同一张表；注入测试只在 tests/。
- 突变/查询分离纪律（连亏重复计数旧回归的教训）：register_trade_result 只改状态，
  check_* 纯查询。

状态机形状近乎照抄旧库 engine_standalone/risk_mgr.py（已验证的纯函数设计），
参数全部来自 config.settings.RISK_PARAMS（= 契约 §2 锁定值）。
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Optional

from config import settings

logger = logging.getLogger(__name__)

P = settings.RISK_PARAMS


# ══ 策略风控状态 ══════════════════════════════════════════════

@dataclass
class StrategyRiskState:
    """单策略风控状态。持久化到 risk_states 表，重启恢复。"""
    name: str
    magic: int
    realized_pnl: float = 0.0
    floating_pnl: float = 0.0
    exit_timestamps: deque = field(default_factory=deque)  # 急速出场窗口
    consecutive_losses: int = 0
    realized_loss_blocked: bool = False
    realized_loss_blocked_at: float = 0.0
    realized_loss_amount_blocked: bool = False
    realized_loss_amount_blocked_at: float = 0.0
    consecutive_loss_blocked: bool = False
    consecutive_loss_blocked_at: float = 0.0
    rapid_exit_blocked: bool = False
    rapid_exit_blocked_at: float = 0.0


# ── 突变（唯一允许改状态的地方）─────────────────────────────

def register_trade_result(state: StrategyRiskState, pnl: float) -> None:
    """单笔结果 → 连亏计数。pnl<0 +1；pnl>0 清零；pnl==0 不变（保本不计不清）。"""
    if pnl < 0:
        state.consecutive_losses += 1
    elif pnl > 0:
        state.consecutive_losses = 0


def record_exit(state: StrategyRiskState, now: float) -> None:
    """出场事件登记（急速出场窗口）。"""
    state.exit_timestamps.append(now)


def mark_blocked(state: StrategyRiskState, gate: str, now: float) -> None:
    """触发某封锁位。gate ∈ {realized_loss, realized_loss_amount, consecutive_loss, rapid_exit}。"""
    if gate == "realized_loss":
        state.realized_loss_blocked, state.realized_loss_blocked_at = True, now
    elif gate == "realized_loss_amount":
        state.realized_loss_amount_blocked, state.realized_loss_amount_blocked_at = True, now
    elif gate == "consecutive_loss":
        state.consecutive_loss_blocked, state.consecutive_loss_blocked_at = True, now
    elif gate == "rapid_exit":
        state.rapid_exit_blocked, state.rapid_exit_blocked_at = True, now
    else:
        raise ValueError(f"未知封锁位: {gate}")


def prune_exit_window(state: StrategyRiskState, window_seconds: int, now: float) -> None:
    """维护窗口（每 tick 主动调用），让 check_rapid_exit 保持纯查询。"""
    while state.exit_timestamps and state.exit_timestamps[0] < now - window_seconds:
        state.exit_timestamps.popleft()


# ── 查询（纯函数，不修改状态）───────────────────────────────

def check_consecutive_loss(state: StrategyRiskState, max_consecutive: int) -> bool:
    return state.consecutive_losses >= max_consecutive


def check_rapid_exit(state: StrategyRiskState, window_seconds: int, max_exits: int, now: float) -> bool:
    cutoff = now - window_seconds
    return sum(1 for t in state.exit_timestamps if t >= cutoff) >= max_exits


def check_realized_loss_amount(state: StrategyRiskState, threshold: float) -> bool:
    return state.realized_pnl <= -threshold


def check_realized_loss_pct(state: StrategyRiskState, balance: float, threshold_pct: float) -> bool:
    if balance <= 0:
        return False
    loss_pct = abs(state.realized_pnl) / balance * 100
    return state.realized_pnl < 0 and loss_pct >= threshold_pct


def is_realized_loss_blocked(state: StrategyRiskState, now: float) -> bool:
    return (state.realized_loss_blocked
            and now - state.realized_loss_blocked_at < P["per_strategy_loss_block_hours"] * 3600)


def is_realized_loss_amount_blocked(state: StrategyRiskState, now: float) -> bool:
    return (state.realized_loss_amount_blocked
            and now - state.realized_loss_amount_blocked_at
            < P["per_strategy_loss_block_hours"] * 3600)


def is_consecutive_loss_blocked(state: StrategyRiskState, now: float) -> bool:
    return (state.consecutive_loss_blocked
            and now - state.consecutive_loss_blocked_at
            < P["consecutive_loss_cooldown_hours"] * 3600)


def is_rapid_exit_blocked(state: StrategyRiskState, now: float) -> bool:
    return (state.rapid_exit_blocked
            and now - state.rapid_exit_blocked_at < P["rapid_exit_cooldown_seconds"])


# ══ 有序门禁表 ════════════════════════════════════════════════

@dataclass
class GateResult:
    blocked: bool
    gate_id: str = ""
    reason: str = ""


GateFn = Callable[[dict], GateResult]
"""门禁函数：接收 context dict（引擎组装），返回 GateResult。抛错 = fail-closed。"""


def _safety_lock_hit(_ctx: dict) -> bool:
    """G0 急停：物理锁文件存在即命中（存在性检查，绝不自动删除）。"""
    import os
    return os.path.exists(settings.SAFETY_LOCK_PATH)


def g0_safety_lock(ctx: dict) -> GateResult:
    if _safety_lock_hit(ctx):
        return GateResult(True, "G0", "safety_lock 文件存在（急停中，人工删除方可解锁）")
    return GateResult(False, "G0")


def g3_global_daily_loss(ctx: dict) -> GateResult:
    day_pnl = ctx.get("day_realized_pnl")
    balance = ctx.get("balance")
    if day_pnl is None or not balance:
        return GateResult(False, "G3")
    loss_pct = -day_pnl / balance * 100
    if day_pnl < 0 and loss_pct >= P["max_daily_loss_pct"]:
        return GateResult(True, "G3", f"全局日亏 {loss_pct:.1f}% ≥ {P['max_daily_loss_pct']}%")
    return GateResult(False, "G3")


def g4_account_floating_loss(ctx: dict) -> GateResult:
    floating = ctx.get("strategy_floating_pnl")
    balance = ctx.get("balance")
    if floating is None or not balance:
        return GateResult(False, "G4")
    pct = -floating / balance * 100
    if floating < 0 and pct >= P["floating_loss_block_pct"]:
        return GateResult(True, "G4", f"浮亏 {pct:.1f}% ≥ {P['floating_loss_block_pct']}%")
    if floating < 0 and pct >= P["floating_loss_warn_pct"]:
        logger.warning("[G4] 浮亏警告 %.1f%%（阈值 %.0f%%）", pct, P["floating_loss_warn_pct"])
    return GateResult(False, "G4")


def g6_state_blocks(ctx: dict) -> GateResult:
    """G6a/G6b：实亏百分比 / 实亏绝对额封锁位检查（触发登记由引擎在平仓回调做）。"""
    state: StrategyRiskState = ctx["risk_state"]
    now = ctx["now"]
    balance = ctx.get("balance") or 0.0
    if is_realized_loss_blocked(state, now):
        return GateResult(True, "G6a", "实亏百分比封锁中")
    if check_realized_loss_pct(state, balance, P["per_strategy_realized_loss_pct"]):
        mark_blocked(state, "realized_loss", now)
        return GateResult(True, "G6a", "实亏 ≥ 5% 余额，封锁 12h")
    if is_realized_loss_amount_blocked(state, now):
        return GateResult(True, "G6b", "实亏绝对额封锁中")
    if check_realized_loss_amount(state, P["per_strategy_realized_loss_amount"]):
        # 盈利回正自动解除的语义：realized_pnl > 0 时 register_trade_result 后会清 blocked
        mark_blocked(state, "realized_loss_amount", now)
        return GateResult(True, "G6b", f"实亏 ≤ -${P['per_strategy_realized_loss_amount']:.0f}，封锁 12h")
    return GateResult(False, "G6")


def g7_consecutive_loss(ctx: dict) -> GateResult:
    state: StrategyRiskState = ctx["risk_state"]
    now = ctx["now"]
    if is_consecutive_loss_blocked(state, now):
        return GateResult(True, "G7", "连亏封锁中")
    if check_consecutive_loss(state, P["max_consecutive_losses"]):
        mark_blocked(state, "consecutive_loss", now)
        return GateResult(True, "G7", f"连亏 {state.consecutive_losses} 次，封锁 {P['consecutive_loss_cooldown_hours']}h")
    return GateResult(False, "G7")


def g8_rapid_exit(ctx: dict) -> GateResult:
    state: StrategyRiskState = ctx["risk_state"]
    now = ctx["now"]
    prune_exit_window(state, P["rapid_exit_window_seconds"], now)
    if is_rapid_exit_blocked(state, now):
        return GateResult(True, "G8", "急速出场封锁中")
    if check_rapid_exit(state, P["rapid_exit_window_seconds"], P["max_rapid_exits"], now):
        mark_blocked(state, "rapid_exit", now)
        return GateResult(True, "G8",
                          f"{P['rapid_exit_window_seconds']}s 内 {P['max_rapid_exits']} 次出场，封锁 2h")
    return GateResult(False, "G8")


def g9_max_positions(ctx: dict) -> GateResult:
    limit = ctx.get("max_positions", P["per_strategy_max_positions"])
    n_open = ctx.get("n_open_positions", 0)
    if limit is not None and n_open >= limit:
        return GateResult(True, "G9", f"并发 {n_open}/{limit}")
    return GateResult(False, "G9")


def g10_same_dir_float_loss(ctx: dict) -> GateResult:
    """同向浮亏禁加仓。旧库为纸面专属；新库全模式生效（并发=1 时与 G9 等价兜底）。"""
    same_dir_pnl = ctx.get("same_dir_floating_pnl")
    if same_dir_pnl is not None and same_dir_pnl < -P["same_dir_float_loss_block"]:
        return GateResult(True, "G10", f"同向浮亏 ${same_dir_pnl:.2f} 禁加仓")
    return GateResult(False, "G10")


def g11_profit_exit_cooldown(ctx: dict) -> GateResult:
    cooldown_until = ctx.get("profit_exit_cooldown_until")  # 该方向冷却截止 UTC 秒，无则 None
    now = ctx["now"]
    if cooldown_until is not None and now < cooldown_until:
        remain_h = (cooldown_until - now) / 3600
        return GateResult(True, "G11", f"盈利平仓冷却，剩余 {remain_h:.1f}h")
    return GateResult(False, "G11")


# G1/G2（新闻）、G5（开市）、G12（K 线门禁）、G13（方向过滤）、G14（MTF）：
# M1 任务 T1.4 接线。故意以"未接线即抛错"呈现——配合 fail-closed，
# 任何在 M1 之前绕过它们的调用都会被拦截而不是放行。
def _m1_stub(gate_id: str) -> GateFn:
    def _gate(_ctx: dict) -> GateResult:
        raise NotImplementedError(f"{gate_id} 未接线（M1 任务 T1.4）")
    return _gate


# 有序表：账户/环境级 → 策略级。评估顺序即契约顺序，勿重排。
GATES: list[GateFn] = [
    g0_safety_lock,          # G0  急停
    _m1_stub("G1"),          # G1  新闻黑屏（M1 接线）
    _m1_stub("G2"),          # G2  新闻偏向封锁（M1 接线）
    g3_global_daily_loss,    # G3  全局日亏硬停
    g4_account_floating_loss,  # G4 账户级浮亏
    _m1_stub("G5"),          # G5  市场开市（M1 接线）
    g6_state_blocks,         # G6a/G6b 实亏封锁
    g7_consecutive_loss,     # G7  连亏封锁
    g8_rapid_exit,           # G8  急速出场封锁
    g9_max_positions,        # G9  并发上限
    g10_same_dir_float_loss, # G10 同向浮亏禁加仓
    g11_profit_exit_cooldown,  # G11 盈利平仓同向冷却
    _m1_stub("G12"),         # G12 K 线门禁（宿主在策略 calc_gate_state，M1 接线）
    _m1_stub("G13"),         # G13 全局方向过滤（M1 接线）
    _m1_stub("G14"),         # G14 MTF 共振（M1 接线）
    # G15 = Athlete 3-tick 复核，属于执行轨，不在本表（engine/athlete.py）。
]


def evaluate(ctx: dict) -> GateResult:
    """有序评估，首个 blocked 即返回。任何门禁抛错 = fail-closed（blocked, gate_error）。"""
    for gate_fn in GATES:
        try:
            result = gate_fn(ctx)
        except Exception as e:  # fail-closed（D8）
            logger.exception("[Gate] 门禁评估异常 → 拦截")
            return GateResult(True, "gate_error", f"{type(e).__name__}: {e}")
        if result.blocked:
            logger.info("[Gate] %s blocked: %s", result.gate_id, result.reason)
            return result
    return GateResult(False, "ALL", "全部门禁放行")
