"""阶段4：分析结论状态对象（仿 core/bias_state 的线程安全模式）。

pa_state.set(direction, cycle_position, trade_confidence, record_path, updated_at, reason)
读取方：① strategies/base.py::calc_gate_state 的可选门控（pa_gate.enabled，默认 off，
仅"neutral 禁开仓"级规则，拦截必写 reason 落 signals.void_reason 同款日志）；
② services/agent/context_builder.py 新增 section（金探聊天自动知道 AI 分析员最新观点）。
"""
