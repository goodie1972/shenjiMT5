"""阶段1/3：后台分析服务（绝不进引擎 10Hz tick 路径）。

模式照 EngineRunner._bias_refresher：
- 独立线程；"K线收盘哨兵"= 最近收盘 M15 棒的 ts_open 变化 → 触发分析（持续跟踪开时增量）；
- CancelToken 贯穿 client/orchestrator；同一时刻仅一轮在跑（_in_flight 防重入）；
- RuntimeConfig 开关：pa.enabled / pa.keep_analysis / pa.auto_gate。
"""
