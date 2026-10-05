# 运维手册（一页纸）

> 日常只需要记住三件事：**看心跳、看日志、跑测试**。细节都在下面。

## 当前在跑什么

| 组件 | 方式 | 存活检查 |
|------|------|----------|
| 引擎（smoke + m15/m30_followave，demo） | 脱离会话进程（supervisor 14 天，至 10-17） | `logs/heartbeat.txt` mtime < 2 分钟 |
| 监控面板（只读，端口 8800） | 脱离会话进程 `tools/run_dashboard.py` | `curl http://127.0.0.1:8800/api/overview` |
| ShenjiWatchdog（计划任务，每 5 分钟） | 心跳陈旧且无进程 → 自动拉起 | `schtasks /Query /TN ShenjiWatchdog` |
| ShenjiBackup（计划任务，每日 20:00） | 打包 journal/db/offset → `../shenjiMT5_backups/`（留 14 份） | 看备份目录新文件 |

## 桌面版打包（PyInstaller）

```powershell
# 构建（需 web/dist 已 build）
python -m PyInstaller ShenjiMT5.spec --noconfirm
# 产物 dist/ShenjiMT5/（onedir 整目录分发）
# 首次部署需把运行时数据拷入安装目录：
robocopy data "dist\ShenjiMT5\data" //E
robocopy config "dist\ShenjiMT5\config" //E //XF runtime_config.json safety_lock.txt
# 启动
dist\ShenjiMT5\ShenjiMT5.exe [--port 8806]
```
也可用根目录 `神机MT5.bat` 双击直接启动（pythonw + run_app，无需打包）。
体积主因 = Python 运行时 + webview + 前端资产（onedir 791MB 属正常）。

## 常用命令

```powershell
# 看引擎是否活着（心跳年龄秒数）
python -c "import os,time;print(int(time.time()-os.path.getmtime('logs/heartbeat.txt')),'s ago')"
# 跟踪日志
tail -f logs\engine.log
# 手动重启引擎（先杀进程）
wmic process where "commandline like '%run_engine%'" call terminate
# 然后看门狗 5 分钟内会自动拉起；或手动：
# powershell Start-Process python -ArgumentList 'tools/supervise_engine.py --smoke --followave --duration 1209600' -WorkingDirectory 'D:\backup\BaoBao\PythonProgram\shenjiMT5' -WindowStyle Hidden
# 全量测试
pytest
# 面板 Playwright 回归（需面板运行中；截图留档 tmp/qa_*.png）
python tools/qa_dashboard.py
# 周报（影子对照）
python tools/weekly_shadow_report.py
```

## 常见故障

| 症状 | 原因 | 处置 |
|------|------|------|
| heartbeat 停止更新 | 进程被杀/电脑重启 | 看门狗 5 分钟内自动拉起；没拉起查 `logs/watchdog.log` |
| 日志大量 `G0 blocked` | safety_lock 急停（含快速平仓自动锁 G0b） | 确认原因后**人工删除** `config/safety_lock.txt` |
| 日志 `G3b 周回撤` | 周亏损 ≥15% 熔断 | 等下周一 UTC 自动解除；复盘当周交易 |
| 下单全被拒 retcode=10xx | 终端"算法交易"没开 / demo 过期 | 终端勾选算法交易；重新登录 |
| 引擎时间错位告警 | broker DST / 时钟 | 校准自动处理；开市后跑 `python tools/probe_mt5.py` 复核 |
| 休市期无日志 | 正常（周末无新 bar） | 周日 21:00 UTC（周一 05:00 UTC+8）自动恢复 |

## 纪律红线

- 同一时间**只跑一个引擎实例**（双开 = 重复下单）。
- 实盘三重确认缺一不可：`settings.ALLOW_LIVE=True` + `config/live_confirm.txt` + 环境变量 `SHENJI_LIVE=1`。
- `config/safety_lock.txt` 只有**人工**能删；任何代码不得自动删它。
- 改风控参数：先改契约 → 再改测试 → 最后改 settings（顺序不可反）。
