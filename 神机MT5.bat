@echo off
rem 神机 MT5 桌面版启动器（双击即启；关窗即停）
rem 依赖：本机 Python + pip install -e .[gui]
cd /d "%~dp0"
start "" pythonw tools\run_app.py --port 8805
