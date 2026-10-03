"""tools/run_engine.py — 引擎运行入口（M1 demo 模式，零真钱）。

用法：
  python tools/run_engine.py --smoke --duration 60   # 冒烟：跑 60 秒
  python tools/run_engine.py --smoke --force         # 无视桶边界强制扫描一次（测试辅助）
  python tools/run_engine.py                          # 正常常驻（Ctrl-C 停）
"""

from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from config import settings
from core.mt5_client import MT5Client
from engine.engine import Engine


def setup_logging(level=logging.INFO):
    """T1.10：控制台 + 文件轮转（5MB × 5），长跑日志不撑爆磁盘。"""
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s",
                            datefmt="%H:%M:%S")
    root = logging.getLogger()
    root.setLevel(level)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)
    os.makedirs(settings.LOG_DIR, exist_ok=True)
    file_h = logging.handlers.RotatingFileHandler(
        os.path.join(settings.LOG_DIR, "engine.log"),
        maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
    file_h.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"))
    root.addHandler(file_h)


def main() -> int:
    parser = argparse.ArgumentParser(description="神机 MT5 引擎（demo）")
    parser.add_argument("--smoke", action="store_true", help="启用 smoke 冒烟策略池")
    parser.add_argument("--followave", action="store_true",
                        help="启用 m15/m30_followave（M3 影子运行，demo 0.01 手）")
    parser.add_argument("--force", action="store_true", help="启动后立即强制全扫描一次")
    parser.add_argument("--duration", type=int, default=0, help="运行秒数（0=常驻）")
    parser.add_argument("--mode", default="demo", choices=["demo"])
    args = parser.parse_args()

    setup_logging()

    pool: dict[str, dict] = {}
    if args.smoke:
        pool["smoke"] = {"magic": 661901, "timeframe": "M5"}
    if args.followave:
        pool["m15_followave"] = {"magic": 661401, "timeframe": "M15"}
        pool["m30_followave"] = {"magic": 661402, "timeframe": "M30"}
    if not pool:
        parser.error("需要至少一个策略池开关（--smoke / --followave）")

    client = MT5Client()
    engine = Engine(client, pool=pool, mode=args.mode)
    engine.start()
    try:
        if args.force:
            stats = engine.force_tick()
            print(f"\nforce_tick → refreshed={stats['refreshed']}")
        end = time.time() + args.duration if args.duration else None
        while end is None or time.time() < end:
            stats = engine.tick()
            if stats["refreshed"]:
                print(f"tick → refreshed={stats['refreshed']}")
            engine._sleep(engine.poll_seconds)
    except KeyboardInterrupt:
        print("\n收到停止信号")
    finally:
        engine.stop()
        client.shutdown()
    print("引擎已停止")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
