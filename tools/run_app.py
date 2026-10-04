"""tools/run_app.py — 神机 MT5 桌面版入口（pywebview 原生窗口，双击即启）。

架构：单进程 = FastAPI（uvicorn 线程）+ pywebview 原生窗口（WebView2 渲染）。
关窗即停。引擎仍为独立进程（看门狗守护）——桌面壳 = 面板进程的原生窗口。

用法：python tools/run_app.py [--port 8805]
打包（后续）：PyInstaller → 神机MT5.exe
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

import uvicorn  # noqa: E402
import webview  # noqa: E402

from dashboard.app import app  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="神机 MT5 桌面版")
    ap.add_argument("--port", type=int, default=8805)
    ap.add_argument("--width", type=int, default=1500)
    ap.add_argument("--height", type=int, default=920)
    args = ap.parse_args()

    url = f"http://127.0.0.1:{args.port}"
    server = threading.Thread(
        target=lambda: uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning"),
        daemon=True)
    server.start()

    # 等服务就绪（最多 20s）
    for _ in range(100):
        try:
            urllib.request.urlopen(url + "/api/overview", timeout=0.5)
            break
        except Exception:
            time.sleep(0.2)

    webview.create_window("神机 MT5 — XAUUSD 量化交易", url,
                          width=args.width, height=args.height)
    webview.start()   # 阻塞至窗口关闭；daemon 服务线程随之退出
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
