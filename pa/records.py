"""阶段1：分析记录落盘 + 增量基线。

- data/pa_records/{ts}_{tf}.json：全量 prompt/响应(含思考)/校验错误/usage（对齐 PA，审计命脉）；
- SQLite 表 pa_records(id, ts, tf, direction, cycle_position, outcome, path) 供面板列表
  与 find_latest_successful_record / compute_incremental_bar_delta（锚定上轮 K1 ts_open）；
- 序列化前递归掩码 API key。
"""
