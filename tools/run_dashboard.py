"""tools/run_dashboard.py — 监控面板入口（v1 纯只读）。

用法：
  python tools/run_dashboard.py                    # 127.0.0.1:8800
  python tools/run_dashboard.py --host 0.0.0.0     # LAN 可见（建议配 DASHBOARD_TOKEN）
"""

from __future__ import annotations

import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

import uvicorn  # noqa: E402

from dashboard.app import app  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="神机 MT5 监控面板（只读）")
    parser.add_argument("--host", default="127.0.0.1",
                        help="默认仅本机；LAN 用 0.0.0.0（建议配 DASHBOARD_TOKEN）")
    parser.add_argument("--port", type=int, default=8800)
    args = parser.parse_args()
    print(f"监控面板 → http://{args.host}:{args.port}/（只读；Ctrl-C 停止）")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
