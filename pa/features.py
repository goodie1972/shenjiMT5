"""阶段0.5：程序预计算 PA 特征（PA 核心思想："程序算得出的不让模型算"）。

输出两张文本表（渲染函数也在本模块）：
1. K线几何表（逐棒）：bar_type（inside/outside > flat > doji > trend_bull/bear 单一优先级）、
   实体比、上下影比、收盘位置、Range/ATR、EMA 关系、与前棒重叠、ii/iii/ioi、缺口、近5棒突破。
2. 市场结构表：摆动点序列、HH/HL（或 LL/LH）计数与分组数、区间边界与测试次数、
   测量移动（MM）候选、Always In 判定（K8–K1 加权同侧占比 + EMA 斜率 + 回撤深度 → AIL/AIS/none + 理由）。

Always In / 摆动计数是决策树 §1.2/§2.3/§2.4 的"程序权威节点"，阶段一 prefill 直接注入。
验收：用 SQLite 历史 ohlcv 离线跑 20 组窗口人工核对。
"""
