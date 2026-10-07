# pa/ — 神机 AI 分析员子系统（自研价格行为分析内核）

本目录是**自包含**的 AI 分析员模块：两阶段价格行为分析（行情诊断 → 交易决策）+ 校验体系，
以"**架构参考 + 自研重写**"方式实现——不携带上游代码、提示词文本、名称与自造术语
（去名称化映射与清洁室纪律见 `docs/移植研究.md` §2）。
设计原则：**所有上游派生内容集中在本目录内**，与神机主体只通过下方"集成面"薄层对接——
便于独立开发测试，也让 AGPL 许可边界保持清晰（见 `docs/PA克隆方案.md` §2、`docs/移植研究.md`）。

## 目录布局

```
pa/
├── README.md               # 本文件
├── docs/移植研究.md          # 移植研究：内核盘点/去名称化映射/MT5 集成面校准/实施阶段
├── docs/PA克隆方案.md       # 早期方案（MT4 时期，集成点名称以移植研究 §3 为准）
├── __init__.py
├── frame_builder.py        # L1 SQLite 闭合K → Frame（B1=最新收盘，forming 不入帧）
├── features.py             # K线几何特征表 + 行情结构（摆动/HH-HL/测量移动/趋势主导态）
├── nodes.py                # 程序规则引擎 R0–R8 + 预检短路应答（新增）
├── contracts.py            # 阶段一/二 JSON 契约常量 + 机器 schema（新增）
├── prompt_assembler.py     # 阶段一/二提示词组装（system 字节级一致 + 4 消息链 + 增量）
├── templates/              # 自命名模板 txt（人设/规则/诊断/核对单/playbook_P*）
├── validator.py            # JSON 五分类校验（SYNTAX/MISSING/SEMANTIC/NO_JSON/QUOTA）
├── normalizer.py           # 宽松修复：围栏/引号/括号/枚举别名/不下单铁律/RR扩stop
├── retry_policy.py         # 分级重试 + NO_RETRY 清单 + 反作弊（不可变字段审计）
├── continuity.py           # 前案一致性检查：限价超时失效/反手冷却/中性单侧（新增）
├── orchestrator.py         # 两阶段流水线：诊断→预检短路→策略路由→决策→落盘
├── llm_client.py           # StreamClient 流式调用（读 data/ai/llm_providers.json）+ 参数剖面
├── pa_state.py             # data/pa/state.json 原子读写（跨进程：供 G12 门控/聊天上下文）
├── records.py              # 每轮 JSON 落盘 data/pa/records/ + index.db 索引
├── service.py              # 面板进程后台线程：收盘哨兵触发 + CancelToken（不进 tick 路径）
└── tests/                  # 单测（特征/校验/修复用历史 ohlcv 离线验证 + test_pa_naming）
```

## 与神机的集成面（唯一的接触点，尽量薄；MT5 现状校准见 `docs/移植研究.md` §3）

| 接触点 | 方向 | 说明 |
|---|---|---|
| `data/database.get_candles()`（L1 只读；引擎持续刷新，DB 即最新） | 神机 → pa | 闭合 K 直读 SQLite；分析只用收盘棒，不需要 forming bar |
| `data/ai/llm_providers.json`（激活项） | 神机 → pa | 复用供应商配置；pa 自带流式 openai 客户端（`llm_client.StreamClient`） |
| `dashboard/wshub.broadcast("pa_analysis", …)` | pa → 神机 | 流式进度/思考 chunk 推前端（pa 线程经 thread-safe 小桥） |
| `data/runtime_config.json` 新 section `pa` | 神机 → pa | `pa.enabled` / `pa_gate.enabled` 等开关（默认全关） |
| `data/pa/state.json`（跨进程结论文件，原子写） | pa → 神机 | 引擎 `calc_gate_state`（G12）读取做可选门控；聊天上下文注入同进程直读 |
| `dashboard/pa_api.py`（扁平路由 + `app.py` include_router） | 神机侧薄胶水 | HTTP 触发/查询转发到 pa.orchestrator（路由文件在 pa/ 之外，属适配层） |

> 宿主事实：引擎（`tools/run_engine.py`，看门狗守护）与面板（`tools/run_app.py`）是**两个进程**；
> pa 服务线程宿主在**面板进程**，与引擎仅通过 `data/pa/state.json` 交互（`docs/移植研究.md` §4.1）。

## 去名称化纪律（硬约束）

代码、模板、UI、新文档中**禁止**出现上游品牌名、包名、类名指纹、自造中文术语与编号体系
（禁字符串清单与映射表见 `docs/移植研究.md` §2）；由 `tests/test_pa_naming.py` 静态卡口强制。
通用交易词汇（swing/breakout/doji/H1H2L1L2 等）不受限。

## 阶段状态

见 `docs/移植研究.md` §5（阶段 0–5，估时 4–6 周）。当前：**阶段 0（数据适配层 + 特征引擎）待动工**。

## 许可提醒

上游项目为 AGPL-3.0。本目录若直接拷贝其源码/提示词文本，神机整体须遵循 AGPL
（自用不分发不触发；对外提供服务或商业分发即触发）。按方案主线的"架构参考 + 自研"
路径实现则无此约束——无论哪种，**上游派生内容只放在本目录内**，别扩散到神机其他模块。
