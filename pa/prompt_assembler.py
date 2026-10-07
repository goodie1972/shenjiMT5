"""阶段1：阶段一/阶段二提示词组装。

templates/ 目录 txt 分层（照搬 PA 分层思想）：
- system_persona.txt（金探 PA 版人设：四禁令/单次分析/只出计划）+ decision_tree.txt（决策树）
  → 两阶段 system 字节级相同（为 KV 前缀缓存）。
- market_diagnosis.txt + kline_dictionary.txt → 阶段一 user；
- bar_checklist.txt + strategy_*.txt（路由加载）→ 阶段二 user；
- output_contracts：阶段一/二 JSON 契约 + 尾部"最后一步必做"提醒（防 schema 漂移的命门）。

K线以定宽文本表注入（最新棒在前，K1=最新收盘，禁引用 K0），特征表附程序权威声明。
增量轮：4 消息链 [system, user(上次S1), assistant(上次S1 JSON), user(增量任务)]，只带新增K线。
"""
