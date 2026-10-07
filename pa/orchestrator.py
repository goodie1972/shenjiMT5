"""阶段1（串行版）→ 阶段3（增量+连续性）：两阶段流水线。

run_analysis(frame, previous_record=None) -> AnalysisRecord：
数据预检 → 阶段一（流式，WS 推思考）→ 校验重试 → 闸门短路（gate=wait/unknown 时程序合成
"不下单"决策，不调第二次 API）→ 策略路由（按 cycle_position+direction 选 strategy_*.txt）→
阶段二 → 校验重试 → 落盘。

事件回调 → web_manager.broadcast("pa_analysis", {...})：
stage_started / reasoning_chunk / content_chunk / stage_done / retry / finished / failed。
"""
