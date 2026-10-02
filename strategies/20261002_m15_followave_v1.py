"""m15_followave v1.0 (MT5 版) — M15 Stoch+BBI+BB 趋势跟踪。

移植血统：旧库 `20260927_m15_followave_v2.py` v1.6（2026-09-27）逐行移植，逻辑与
M30 版完全同源（diff 仅差 TRAIL_ATR=4.0 / magic / 周期）；适配点见 followave_core 头注。

准源纪律：MT4 版仍为策略唯一准源，T2.6 对账达标前禁改参数。
"""
from strategies.followave_core import FollowAveCore

STRATEGY_MAGIC = 661401      # 沿用旧库号段
STRATEGY_VERSION = "v1.0"
STRATEGY_CHANGELOG = [
    {"version": "v1.0", "magic": 661401, "date": "2026-10-02",
     "desc": ("MT5 版首发：逐行移植旧库 v1.6（逻辑/参数零改动，与 m30 版同源共享"
              " followave_core）。T2.6 对账达标前禁改参数")},
]


class M15FollowAveStrategy(FollowAveCore):
    """M15 FollowAve — TRAIL_ATR=4.0（M15 回测优化值，v1.2 定）"""

    name = "m15_followave"
    TIMEFRAME = "M15"
    TRAIL_ATR = 4.0
