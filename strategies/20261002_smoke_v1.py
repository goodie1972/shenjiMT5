"""20261002_smoke_v1.py — M1 冒烟策略（T1.9 的白盒探针）。

目的：验证 取数→指标→打分→门禁→入库 全管道，不追求盈利。
逻辑（全部白盒、只用白名单键）：bar1 阳线 且 RSI(14) < 35 → BUY。
纪律：STRATEGY_MAGIC/VERSION/CHANGELOG 齐备；旧版移 backup/；逻辑改动 changelog +1。
"""

from strategies.base import BaseStrategy

STRATEGY_MAGIC = 661901
STRATEGY_VERSION = "v1"
STRATEGY_CHANGELOG = [
    {"version": "v1", "date": "2026-10-02",
     "desc": "M1 冒烟：bar1 阳线 + RSI<35 → BUY。仅验证信号管道，非盈利策略"},
]


class SmokeStrategy(BaseStrategy):
    name = "smoke"

    def generate_signal(self):
        bar1 = self.bar1()
        rsi = self.get_indicator("rsi")
        values = {"rsi": rsi}
        if bar1 is None or rsi is None:
            return (None, 0, 0, [], [], values)
        if bar1.close > bar1.open and rsi < 35:
            return ("BUY", 1, 0,
                    [f"bar1阳线({bar1.close:.2f}>{bar1.open:.2f})", f"rsi={rsi:.1f}"],
                    [], values)
        return (None, 0, 0, [], [], values)
