"""m30_followave v1.0 (MT5 版) — M30 Stoch+BBI+BB 趋势跟踪。

移植血统：旧库 `20260927_m30_followave_v2.py` v1.6（2026-09-27）逐行移植，逻辑与
参数零改动；适配点清单见 `strategies/followave_core.py` 头注（接口换血，共 6 条）。

准源纪律：MT4 版仍为策略唯一准源。T2.6 重叠期对账（信号方向一致率 ≥95%）达标前，
本文件任何参数都禁改；改动必须先发生在 MT4 版并记 changelog，再 rebase 过来。

回测依据（继承旧库 changelog，详见旧库文件头注与
strategies/docs/strategies/followave_improvement_analysis.md）：
- v1.3 入场 80/20（撤销 70/30）、方向过滤维持 bb_mid_direction（SMA20 斜率）
- v1.4 DI_GATE 5→2
- v1.5 分批止盈 3.0×ATR(入场冻结) 平 50%，每笔一次
- v1.6 出场八分支归因（_last_exit_detail）
"""
from strategies.followave_core import FollowAveCore

STRATEGY_MAGIC = 661402      # 沿用旧库号段（PP=66, NN=14, VV=02）
STRATEGY_VERSION = "v1.0"
STRATEGY_CHANGELOG = [
    {"version": "v1.0", "magic": 661402, "date": "2026-10-02",
     "desc": ("MT5 版首发：逐行移植旧库 v1.6（逻辑/参数零改动）。接口适配 6 条见 followave_core"
              " 头注；指标本地计算（Wilder/MT4 标准公式）。MT4 版为唯一准源，T2.6 对账达标前禁改参数")},
]


class M30FollowAveStrategy(FollowAveCore):
    """M30 FollowAve — TRAIL_ATR=3.0（M30 回测优化值，v1.2 定）"""

    name = "m30_followave"
    TIMEFRAME = "M30"
    TRAIL_ATR = 3.0
