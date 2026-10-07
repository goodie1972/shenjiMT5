"""阶段0：DataFactory K线缓存 → PA KlineFrame。

职责（见 docs/PA克隆方案.md §4.1）：
- 从 services.data_factory.get_cache(tf)["candles"] 取 K 线（[-1]=forming, [-2]=最新收盘）；
- 转成 PA 约定的 KlineBar(seq, ts_open_ms, ohlcv, closed)：seq=1 为最新收盘 K，forming bar 为 seq=0 且 closed=False；
- 自算 EMA20 / ATR14（神机缓存是 ema_21，不能直接用）；
- 分析门槛：≥20 根收盘 K 且指标非 NaN（PA 约定），否则抛 InsufficientData。

注意坑：H4 桶按 timestamp % 14400 == 3600 对齐；MT4 服务器时钟比真 UTC 快约 30 分钟
（引擎 _calibrate_mt4_time 已校准，分析窗口一律用 K 序号，不依赖绝对时间）。
"""
