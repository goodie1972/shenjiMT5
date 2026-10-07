# PA Agent → 神机（MT4 版）克隆方案

> 目标：把 PA Agent（PyQt6 桌面版 AI 价格行为分析工具）的核心能力——**两阶段结构化分析 + 校验体系**——克隆进神机 XAUUSD 系统（`xauusd`），让"金探"从聊天分析师升级为**可审计、可门控的 AI 分析员**。
> 配套阅读：`D:\backup\BaoBao\PythonProgram\PA_Agent-main\PA_Agent架构拆解.md`（PA 全架构 + 提示词全文 + 决策树）。

---

## 0. 结论摘要（TL;DR）

1. **高度可行**。神机的数据底座（DataFactory 的 K 线缓存 + 83 项指标 + SQLite）能直接喂出 PA 需要的 100 根收盘 K 线；PA 的核心资产（提示词库、校验体系、两阶段编排）是**纯 Python + 文本**，不依赖 PyQt6，可整体移植到神机的后台服务层。
2. **神机已有一半基础设施**：多供应商 LLM 管理（含故障转移/SSRF 防护）、对话式 Agent（金探 + 工具 + 记忆）、以及唯一一条"LLM→交易决策"链路（新闻判向 → `bias_state` 门控）——**PA 克隆完直接复用这层接线模式**。
3. **神机缺的恰好是 PA 的灵魂**：无两阶段编排、无 schema 校验/宽松修复/反作弊、无程序预计算 PA 特征、无逐轮落盘审计。
4. **最大决策点不是技术，是许可证**：PA 是 AGPL-3.0，直接拷代码有传染义务（见 §2）。本方案按"**架构参考 + 自研实现**"为主线设计（给出模块映射表），拷贝代码仅作为自用场景的快捷选项。
5. **交易联动必须保守**：先 advisory（面板展示）→ 再方向门控（扩展现有 `bias_state`，默认关闭）→ 最后才考虑直接信号。风控链完全沿用神机现有 Athlete/风控闸门，PA 永远不绕过它。

---

## 1. 两系统现状对照

| 能力 | PA Agent（现状） | 神机 xauusd（现状） | 差距结论 |
|---|---|---|---|
| K 线数据 | MT5/TV/AkShare 多源 + KlineFrame（K1=最新收盘） | FreeMT4Bridge EA → DataFactory 缓存（M15/M30/H1/H4+合成H2，2000根/周期）+ SQLite | **神机更强**，PA 数据层整个不用搬 |
| 指标 | 自研 EMA20/ATR14（含增量状态机） | EA F043 63 项 + TA-Lib 83 项（含 ema_21、atr） | 神机缺 EMA20，自算即可（几行代码） |
| PA 预计算特征 | K线几何（bar_type/影线比/重叠/ii-iii…）+ 市场结构（摆动/HH-HL 计数/测量移动）+ Always In 五信号投票 | **完全没有**（只有 RSI/MACD 数值快照） | ★ 核心移植点 1 |
| 提示词工程 | 30 个 txt：人设/二元决策树/诊断框架/22 策略文件 + 13 个代码内契约 | soul.md 人设（26 行，advisory）+ 1 个 market_analysis 技能大纲 | ★ 核心移植点 2（需 XAUUSD 语境适配） |
| 两阶段编排 | 阶段一诊断 → 闸门 → 策略路由 → 阶段二决策，支持 KV 前缀链、增量链 | 无（聊天即问答；新闻判向是单轮批处理） | ★ 核心移植点 3 |
| 校验体系 | 错误五分类(a-e) + 宽松修复 + 枚举别名 + 闸门轨迹一致性 + 交易方程 + 反作弊审计 | 单笔复盘 JSON 只有"宽松解析+降级" | ★ 核心移植点 4 |
| 记录审计 | 每轮一个 JSON（prompt/响应/错误/token 全存） | signals/trades 表 + logs | 移植后落 SQLite/JSON 均可 |
| LLM 调用层 | DeepSeekClient：流式、thinking 参数按网关适配、max_tokens 按网关、KV 缓存统计 | LLMProviderManager v5：多 Provider 注册/激活/故障转移，**非流式**、无思考流 | 各有优势，见 §4.3 决策 |
| 增量 + 连续性 | 增量链（只发新K线）+ 上轮方案连续性卫兵（自动撤限价单/反手冷却） | 无 | 阶段 3 移植 |
| 交易联动 | 无（纯 advisory，不下单） | 完整下单/风控/出场链 + bias_state 门控先例 | **互补**：PA 出观点，神机管执行 |
| 前端 | PyQt6 桌面（决策树动画/流式窗/图表叠加） | Vue3 + lightweight-charts + SSE/WS | 不搬 GUI，重写面板（PA 的表达层设计可抄） |

---

## 2. 许可证决策（先做这个决定）

PA Agent 是 **AGPL-3.0**。三种路径：

| 路径 | 做法 | 后果 | 适用 |
|---|---|---|---|
| A. 直接拷代码 | 把 PA 的 ai/、orchestrator/ 源码拷进神机 | 神机整体需按 AGPL-3.0 开源（自用不分发不触发；**对外提供服务或商业分发即触发**） | 纯自用、不在乎开源 |
| B. 架构参考 + 自研（**推荐**） | 依据《PA_Agent架构拆解.md》重新实现，提示词按"结构自写、术语自查" | 版权干净；工作量约多 30–40%（架构文档已把设计决策、坑、接口都写清，实际增量可控） | 神机可能商业化/闭源 |
| C. 进程隔离 | PA 克隆做成独立 FastAPI 服务（AGPL），神机经 HTTP 调用 | 边界清晰但有争议；多一个部署单元 | 折中 |

> 注意：**提示词 txt 同样是 AGPL 内容**，逐字拷 30 个文件 = 拷贝代码。路径 B 下应"参考结构重写"（决策树的节点逻辑、闸门顺序这些方法论不受版权保护，文字表达要自己写）。
> 下文按路径 B 叙述；选路径 A 时把"自研"替换为"移植"即可，接口设计不变。

---

## 2.5 目录布局与隔离原则（自包含子目录）

所有 PA 派生内容集中在 **`xauusd/pa/`** 一个子目录内，不散落进神机现有模块：

```
xauusd/pa/
├── README.md               # 模块章程 + 集成面清单
├── docs/PA克隆方案.md       # 本文档
├── frame_builder.py  features.py  prompt_assembler.py  templates/
├── validator.py  normalizer.py  retry_policy.py
├── orchestrator.py  llm_client.py  pa_state.py  records.py  service.py
└── tests/
```

- **好处 1（许可证）**：若选路径 A（直接拷 PA 代码），AGPL 派生内容物理隔离在本目录，未来切换许可证/剥离该功能时边界清晰。
- **好处 2（可独立测试）**：pa/ 只依赖 DataFactory 只读接口与 llm_providers.json，可用 SQLite 历史 ohlcv 离线开发，不启动引擎也能跑通校验与编排单测。
- **好处 3（可拆卸）**：整个功能 = pa/ 目录 + 三个薄胶水点（routes/pa_analysis.py 转发、WS channel、calc_gate_state 可选钩子），删目录即下线。
- **纪律**：神机其他模块**禁止** import pa/ 之外的任何 PA 派生内容；pa/ 对神机只读（除 pa_state 与 pa_records 两个明确写入点）。

（骨架已建好：各模块为带职责说明的 stub，按 §5 阶段逐个填充。）

## 3. 目标架构

```
                        ┌────────────────── 神机现有（不动）──────────────────┐
MT4 终端 + FreeMT4Bridge EA                                            Vue3 面板
        │ F042/F043/F020                                        FastAPI :1783
        ▼                                                             ▲
DataFactory 线程 → _DATA_CACHE(tf candles+indicators) → SQLite      WebSocket /ws
        │                                                            │ channel: pa_analysis
        ▼                                                            │
┌─────────────────── 新增：pa/ 子目录（AI 分析员子系统，自包含）─────────────┴────────────┐
│  frame_builder      K线缓存 → PA KlineFrame（K1=最新收盘，切 forming bar）         │
│  feature_engine     移植 PA 思想：K线几何特征表 + 市场结构(摆动/HH-HL/MM) + AlwaysIn │
│  prompt_assembler   阶段一/阶段二提示词组装（templates/ 目录 txt 化管理）           │
│  orchestrator       两阶段流水线：诊断→闸门→策略路由→决策→校验→重试（后台线程）      │
│  validator          JSON 五分类校验 + 宽松修复 + 枚举别名 + 一致性检查 + 反作弊      │
│  pa_state           分析结论状态对象（仿 bias_state：direction/confidence/记录路径）│
│  llm_client         流式调用（接 LLMProviderManager 的激活 Provider）+ 网关适配表  │
│  records            每轮 JSON 落盘 data/pa_records/ + SQLite 索引                 │
└──────────────────────────────────────────────────────────────────────────────┘
        │ pa_state.set(direction, cycle_position, decision)          │ WS 推流式进度
        ▼                                                            ▼
  [阶段4 可选] strategies/base.py 的 calc_gate_state 读 pa_state      routes/pa_analysis.py
  （方向门控，默认关闭，RuntimeConfig 开关）                          前端 /analysis 视图 + 图表标注
```

**关键原则**：
- **不进 tick 路径**。LLM 调用 30s+，绝不放进 10Hz 引擎循环（引擎单 tick 预算 280ms）。分析跑在独立后台线程， mimic `EngineRunner._bias_refresher` 的模式：**K 线收盘哨兵触发**（M15 收盘 → 若开启持续跟踪则提交增量分析）。
- **PA 永远 advisory-first**。其结论流向：① 面板展示（默认）→ ② `pa_state` 门控（RuntimeConfig 开关，默认 off）→ ③ 直接产出信号进 Athlete（远期，且必须带置信度阈值与风控复检）。

---

## 4. 模块映射与实现要点

### 4.1 数据适配层（阶段 0，约 2 天）

PA 的 `KlineBar(seq, ts_open, ohlcv, closed)` / `KlineFrame` 直接照抄数据结构定义（几十行 dataclass，接口约定不构成版权问题）：

```python
# pa/frame_builder.py（自研，结构对齐 PA data/base.py）
def build_frame(tf: str = "M15", count: int = 100) -> KlineFrame:
    candles = data_factory.get_cache(tf)["candles"]   # [-1]=forming, [-2]=最新收盘
    bars = [KlineBar(seq=len(closed)-i, ts_open=c.time, ...) for i, c in enumerate(closed)]
    ema20 = compute_ema(closes, 20); atr14 = compute_atr(bars, 14)   # 自算，神机缓存里是 ema_21
```

**MT4 特有坑（务必处理）**：
- **H4 桶对齐**：神机 H4 按 `timestamp % 14400 == 3600` 对齐（01:00 UTC 起桶），不是自然日切——做周期聚合/展示时注意。
- **服务器时钟偏移**：MT4 服务器比真 UTC 快约 30 分钟，引擎已有 `_calibrate_mt4_time`（6h 重校准）——PA 的时间窗切分（K40–K1/K8–K1）用**序号**而非绝对时间，天然免疫此问题；但展示层要过 `_mt4_to_local`。
- **分析门槛**：PA 要求 ≥20 根收盘 K + EMA/ATR 非 NaN；神机缓存 2000 根/周期，M15 完全够。主周期建议 **M15**（PA 默认 15m，XAUUSD 15m 结构清晰），同时注入 H1 作长程背景（PA 的三层窗口本来就是同一份数据的切分，可先用单周期 100 根起步）。

### 4.2 特征引擎（阶段 0.5，约 3–4 天，路径 B 的最大自研块）

按 PA 的思想自研（`pa/features.py`），输出两张文本表：

1. **K 线几何表**（逐棒）：bar_type 分类（inside/outside > flat > doji > trend_bull/bear 的单一优先级）、实体比、上下影比、收盘位置、Range/ATR、EMA 关系、与前棒重叠度、ii/iii/ioi、缺口、近 5 棒突破。
2. **市场结构表**：摆动点序列、HH/HL（或 LL/LH）计数与分组数、区间上下边界与测试次数、测量移动候选、**Always In 判定**（近端 K8–K1 加权同侧占比 + EMA 斜率 + 回撤深度，AIL/AIS/none 三态 + 理由）。

> Always In 和摆动计数是决策树 §1.2/§2.3/§2.4 的"程序权威节点"——这一步做扎实，阶段一 hallucination 至少减半。测试策略：用神机 SQLite 里的历史 ohlcv 跑特征，人工核对 20 组窗口。

### 4.3 LLM 调用层（阶段 1 内完成，1 天 + 按需增强）

- **起步**：直接用 `llm_provider.get_llm_manager().chat(messages)`（多 Provider 故障转移白拿）——但它**非流式、不返回 reasoning_content**。
- **增强（建议直接做）**：`pa/llm_client.py` 自带 openai SDK 流式调用，激活 Provider 从 `data/llm_providers.json` 读（复用其密钥管理/激活状态/SSRF 判定），流式 chunk 经 WS `pa_analysis` channel 推给前端（对应 PA 的思考流窗口）。顺带把 PA 的**网关适配表**搬过来：thinking 参数格式（sensenova `enabled/disabled/auto`、deepseek v4 `adaptive+output_config.effort`、anthropic `budget_tokens`）与 max_tokens 上限表——神机用户同样会用各种中转站，这套表是踩坑换来的。
- **KV 前缀链**：阶段 3 再上（system 消息两阶段字节级相同 + 增量轮 4 消息链），DeepSeek 官方 API 缓存命中可省 60%+ 输入费；中转站不支持也无害。

### 4.4 提示词库（阶段 1，约 3–4 天，路径 B 下重写）

目录：`pa/templates/*.txt`，结构照搬 PA 的分层（这套分层本身就是精髓）：

| 神机文件 | 对应 PA | 说明 |
|---|---|---|
| `system_persona.txt` | 提示词大纲 | 重写为"金探"PA 版：概率思维/四禁令/单次分析/只出计划不下单 |
| `decision_tree.txt` | 二元决策.txt（1101 行） | **方法论照用，文字自写**：八态周期 → 方向 → 尖峰/通道/区间 → §9 入场信号 → §10 风险收益（含 10.3 交易者方程）→ §11 下单方式 → §14 禁令。**注意修复 PA 已知三处缺陷**：RR 扩 stop 阈值统一为 1.0；"止损单"改叫"突破单"；§14 删掉单次分析不可执行的两条 |
| `market_diagnosis.txt` | 市场诊断框架 | 八态频谱定义 + 统一判定树 + 三窗口（XAUUSD 15m 下窗口切分同 PA：K{n}–K41 / K40–K1 / K8–K1） |
| `bar_checklist.txt` | 逐棒分析检查单 | 阶段二逐棒纪律 |
| `strategy_*.txt` | 22 个策略文件 | **按需精简**：XAUUSD 15m 高频使用的先写 8 个左右（震荡区间对、通道对、极速对、突破失败、二次入场、止损止盈、MM），其余路由到了再补 |
| `output_contracts.py` | prompt_assembler 13 个常量 | 阶段一/二 JSON 契约 + 尾部提醒（这是防 schema 漂移的命门，字段名与 validator 强对齐） |

**XAUUSD 适配**：PA 文本里的"1跳"→ 明确定义 `1 tick = 0.01 USD`（或改用 0.1×ATR 表述）；无 A股语境问题，Brooks PA 对黄金完全适用；`bar_by_bar_summary 恰好5条`等 schema 硬约束原样保留。

### 4.5 校验与修复（阶段 2，约 8–10 天，工作量最大、价值最高）

按 PA 的五分类体系自研 `pa/validator.py` + `normalizer.py` + `retry_policy.py`：

- **分类**：a=语法（含截断修复）/ b=缺字段 / c=枚举与跨字段语义 / d=无JSON / e=配额错误（不重试）。
- **修复流水线**：剥围栏 → 智能引号 → 括号配平 → 枚举别名表（做多/long/bullish、限价→限价单…）→ `不下单 ⇔ 五价全 null` 双向铁律 → 突破价吸附 → RR>1.0 自动扩 stop → 连续性卫兵强转不下单。
- **一致性检查**：闸门轨迹（节点顺序/bar_range 格式/不得引用 K0）、逐棒 bar_type 与程序特征一致性（**自动纠正**而非报错）、突破单基准极值、概率和 ∈[99,101]、交易者方程（RR≥1.0 + 胜率方程，用真实三价算）。
- **反作弊**：重试成功后比对 `direction`/`cycle_position` 不可变，豁免条件=增量声明/程序节点，违规立即失败不再重试。
- **重试策略**：a/b/d 全额重试；c 一次；`metrics:` 类**禁止**自动重试（防硬凑价格）。

### 4.6 编排器 + 记录（阶段 1 先做串行版，阶段 3 加增量）

`pa/orchestrator.py`：`run_analysis(frame, previous_record=None) -> AnalysisRecord`，流程照 PA：数据预检 → 阶段一（流式，WS 推思考）→ 校验重试 → 闸门短路（wait/unknown 程序合成决策，不调第二次 API）→ 策略路由 → 经验注入（可后置）→ 阶段二 → 校验重试 → 落盘。事件用简单回调 → `web_manager.broadcast("pa_analysis", {...})` 推前端。

记录：`data/pa_records/{ts}_{tf}.json`（对齐 PA，含全量 prompt/响应/错误/usage），SQLite 加一张 `pa_records(id, ts, tf, direction, cycle_position, outcome, path)` 索引表供面板列表与增量基线查询（`find_latest_successful_record` 等价物）。

### 4.7 交易联动（阶段 4，约 2–3 天，默认全部关闭）

1. `pa/pa_state.py`：仿 `bias_state` 的线程安全三态 + `cycle_position` + `trade_confidence` + 更新时间。
2. 门控接入点（可选开关 `pa_gate.enabled`，默认 false）：在 `strategies/base.py::calc_gate_state` 里加一个与 News-Bias 并列的检查——`pa_state.direction=neutral` 时禁止顺势开仓（或仅告警）。**不动 Athlete、不动风控链、不动出场逻辑**。
3. 反向通道：把 `pa_state` 注入现有 ContextBuilder（`context_builder.py` 的 sections 加一段），金探聊天自动"知道"AI 分析员的最新观点。

### 4.8 前端面板（阶段 5，约 3–4 天）

- 新路由 `/analysis`（`views/AnalysisView.vue` + AppShell 菜单 + Pinia `stores/pa.ts`）。
- 布局照 PA 表达层：左侧 K 线（TradingTerminal 复用，叠加 entry/TP/SL 横线——`BacktestKlineChart.vue` 的 SeriesMarker 模式已有先例）；右侧三个 Tab：实时流（SSE/WS 思考流 + 正文）、决策卡（order_type/三价/置信度/推理）、原始记录（阶段 prompt/响应/校验错误查看，含重试轮次）。
- WS channel `pa_analysis` 推：`stage_started / reasoning_chunk / content_chunk / stage_done / retry / finished / failed`。
- 按钮：立即分析 / 增量分析 / 持续跟踪（K 线收盘哨兵）/ 取消（CancelToken）。

---

## 5. 实施阶段与工作量

| 阶段 | 内容 | 估时（单人） | 验收标准 |
|---|---|---|---|
| 0 | 数据适配层 + 特征引擎 + 单测（用历史 ohlcv 离线验证特征正确性） | 4–5 天 | 任意历史窗口输出正确的几何表/结构表/AlwaysIn |
| 1 | MVP 管线：提示词库（8 个策略文件起步）+ 串行两阶段 + 五分类校验（先只做 a/b/d + 基础 c）+ 落盘 + curl 可调 | 6–8 天 | XAUUSD M15 真实数据端到端出决策 JSON，10 轮零语法错误 |
| 2 | 完整校验：宽松修复 + 一致性检查 + 反作弊 + 分级重试 + 网关适配表 | 8–10 天 | 弱模型（flash 档）10 轮增量测试，schema 漂移全部被修复或干净失败 |
| 3 | 增量链 + 连续性卫兵 + 闸门短路 + KV 前缀链 + 流式 WS | 4–5 天 | 增量轮 prompt token 比全量省 40%+；上轮限价未成交正确自动撤销 |
| 4 | 交易联动：pa_state + 门控开关（默认关）+ 金探上下文注入 | 2–3 天 | 开关门控生效/关闭零影响；模拟盘 1 周无异常拦截 |
| 5 | 前端 /analysis 面板 + 图表标注 + 持续跟踪 UI | 3–5 天 | 面板完整走通一次分析并展示标注 |

合计约 **4–6 周**（路径 B）；选路径 A（直接拷 PA 代码）阶段 1/2 可压缩一半，但需先接受 §2 的许可证结论。**建议第 1 阶段结束就上模拟盘跑观察**（神机 PaperBridge 现成），用真实流喂校验器。

---

## 6. 风险与已知坑（全部来自实测）

1. **弱模型 schema 漂移**：PA 实测 flash 档模型首次全量正常、**增量重分析时照抄阶段一格式**（PA 的输出契约+尾部提醒都拦不住）。对策：校验体系必须先行（阶段 2 提前）；持续跟踪模式建议配强模型；保留"失败即弹原始响应"的调试路径。
2. **中转站网关**：`/v1/models` 常为空、模型 ID 是非标准别名、token 套餐有模型白名单（403）。上线前用 1-token 请求探活；网关适配表（thinking 参数/max_tokens）直接搬 PA 的。
3. **`metrics:` 类错误禁止自动重试**：实测模型会为凑 RR 修改止损——自动重试会放大而非解决问题。保留 PA 的 NO_RETRY 清单设计。
4. **H4 时区/时钟偏移**：见 §4.1；所有分析内窗口用 K 序号，展示才转本地时间。
5. **LLM 成本**：两阶段全量约 PA 实测 10–20 万 prompt tokens/轮（前缀链后增量轮省 60%）。神机 LLMProviderManager 已统计调用，建议把 PA 的 usage 累加进同一口径。
6. **门控误杀**：pa_gate 初期只做"中性禁开仓"这类低风险规则，且每次拦截必须写明 `pa_state.reason` 落日志（神机 signals 表的 void_reason 模式现成）；观察 2 周后再考虑更激进的置信度门控。
7. **AGPL**：见 §2，别在写完代码后才想起来。

---

## 7. 下一步（本周可做）

1. 拍板 §2 许可证路径（A/B/C）。
2. ~~阶段 0 动工：`pa/` 骨架~~（**骨架已建**：`xauusd/pa/`，各模块为带职责说明的 stub）→ 填充 `frame_builder` + 特征引擎 + 用 SQLite 历史 ohlcv 写特征单测。
3. 把《PA_Agent架构拆解.md》附录 A（决策树全文）打印出来做重写底稿——**决策树的节点结构与闸门顺序是整个系统的骨架，值得先在纸上过一遍再动笔**。
4. 建一个 `docs/PA_PORTING_LOG.md`，每个阶段记录"PA 怎么做 → 我们怎么做 → 差异原因"，方便后续升级时对齐上游改进。
