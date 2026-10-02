# 神机 MT5 版（shenjiMT5）

XAUUSD 量化交易系统，从 MT4 版（`D:\backup\BaoBao\PythonProgram\xauusd`，只读参考）另起的干净重写：
**与旧库共享契约、不共享代码**；三轨引擎（DataFactory → 策略员 → Athlete）跑在 MetaTrader5 官方 Python API 上。

## 文档

| 文档 | 内容 |
|------|------|
| [docs/PRD.md](docs/PRD.md) | 决策、内核定义（迁移/丢弃清单）、语义决策 D1~D8、过渡政策、风险登记册 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 三轨架构、模块映射、数据流、时区模型、技术选型 |
| [docs/EXECUTION_PLAN.md](docs/EXECUTION_PLAN.md) | M0~M3 任务与验收、过渡期铁律、当前进度 |
| [docs/contracts/](docs/contracts/README.md) | 三契约（策略/数据/风控）— 两仓库唯一共享物 |

## 快速开始

```powershell
# 0) 前置：Windows + 64 位 Python 3.10+；MetaTrader 5 终端已安装并登录 demo 账户
# 1) 安装
pip install -e .[dev]
# 2) 环境探测（M0 第一步；输出 docs/probe/mt5_probe_report.md）
python tools/probe_mt5.py
# 3) 契约测试
pytest
```

## 里程碑状态

- [x] M0 骨架（文档 + 契约 + 骨架 + probe 脚本）
- [ ] M0 探路 + 数据入库（见 EXECUTION_PLAN.md T0.4 起）
- [ ] M1 demo 全链路
- [ ] M2 FollowAve 移植 + 基线重建
- [ ] M3 逐策略晋升

## 纪律入口

给人与 AI 助手的最高优先级约定在 [AGENTS.md](AGENTS.md)：UTC 时间纪律、只读分层、bar1/白名单、门禁 fail-closed 且无模式旁路、根目录净空。
