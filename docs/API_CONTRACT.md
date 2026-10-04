# API 契约 — 旧前端（web/）↔ 新后端（FastAPI）

- 版本：v1.0（2026-10-04）
- 目的：E 路线 UI 完成的**端点差距清单与实现顺序**。前端为旧库 fork（44 个静态端点 + 动态构造家族），本契约按"家族"管理——实现一个家族点亮一批页面。
- 变更流程：前端新增/改动端点调用必须先在本文件登记家族与状态。

## 1. 家族级差距表（按实现顺序）

| # | 家族 | 前端用途 | 新后端状态 | 期 |
|---|------|----------|-----------|-----|
| 1 | `/api/positions`（+ `/{ticket}/close`、`/{ticket}/modify`） | 交易终端/持仓管理 | **部分**（queries 有数据；缺 REST 端点与写操作→mt5_client） | U-E1 |
| 2 | `/api/signals/latest` 等 | 信号面板 | **部分**（signals 表已有） | U-E1 |
| 3 | `/api/data/candles`、`/api/market/candles` | K 线终端 | **部分**（`/api/candles` 已有，需对齐前端参数形状） | U-E1 |
| 4 | `/api/account/*` | 账户面板 | **部分**（account_summary 已有） | U-E1 |
| 5 | `/api/trades/history`、`/api/trades/stats` | 历史成交/stats | **部分**（trades 表已有；stats 按旧库口径补） | U-E1 |
| 6 | `/api/engine/health`、`/api/engine/start|stop|restart` | 巡检/启停 | **缺**（控制通道：面板进程→引擎进程） | U-E2 |
| 7 | `/api/config/*`（risk/news/paper/strategy-pool） | 运行配置 | **缺**（runtime.json 移植） | U-E2 |
| 8 | `/api/strategies/available`、`/logics`、`/batch-remove` | 策略中心 | **缺**（scanner 已有） | U-E2 |
| 9 | WebSocket hub（prices 0.3s/positions 5s/account 10s/logs 1s） | 实时刷新 | **缺**——首版前端轮询降级，后补**同通道名** WS | U-E2 |
| 10 | `/api/reports/*`、影子对照 Tab | 日报周报 | **部分**（weekly_shadow_report 脚本已有，需 REST 化） | U-E3 |
| 11 | `/api/backtest/*`（run/status/results/history/indicators） | 回测中心 | **缺**（D3 回测框架 + 子进程作业） | U-E3 |
| 12 | `/api/news/calendar`、`/api/news/gold` | 新闻日历/G1 | **缺**（ForexFactory 抓取移植） | U-E3 |
| 13 | `/api/ai/*`（chat SSE/persona/skills/agent-settings）+ `/api/llm/*` | AI agent | **缺**（D5/D6：底座重写 + PA 工具 + sidecar） | U-E4 |
| 14 | `/api/mcp/*`、`/api/ai/skill-store/*` | MCP/技能市场 | **决策不做**（v1；需要时按旧库 682 行设计加回） | — |
| 15 | `/api/version/*` + 自动更新 | 更新器 | **决策不做** | — |

前端配套改造（fork 源码级，随对应家族实施）：
- API 基址指向新后端（默认同源，零配置）
- WS 断连降级为轮询（client/websocket.ts 已有重连逻辑，加降级开关）
- ReportView 加影子对照 Tab（override.js v2 已演示）
- 策略中心分组/搜索、日报时间线聚合（治理①②）
- FortuneCat 保留为 AI agent 入口

## 2. 实现纪律

1. 端点响应形状**以旧后端为准**（前端零改动或少改动优先于后端优雅）。
2. 每实现一个家族：`pytest` 全绿 + 面板 Playwright 回归 + 本文件状态更新。
3. 只读端点直接映射现有 queries/DB；写端点（close/modify/engine 控制）走确认+journal 纪律。
4. WebSocket 通道名与旧库一致（prices/positions/account/logs/engine），便于前端零改动切换。

## 变更记录

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-10-04 | 初版：家族级差距表（15 族）+ 实现顺序 U-E1~E4 + 纪律 |
