"""tools/supervise_engine.py — 引擎监督器（T1.10）：崩溃自动重启，跑满时长自动收工。

用法（72h 冒烟）：
  python tools/supervise_engine.py --smoke --duration 259200

策略：子进程异常退出 → 指数退避重启（30s 起步，翻倍封顶 10 分钟，上限 max-restarts）；
正常退出（duration 到点 / Ctrl-C）→ 直接收工。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    parser = argparse.ArgumentParser(description="引擎监督器")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--duration", type=int, default=0, help="总运行秒数（0=常驻）")
    parser.add_argument("--max-restarts", type=int, default=20)
    args = parser.parse_args()

    t0 = time.time()
    restarts, backoff = 0, 30
    while True:
        remaining = args.duration - (time.time() - t0) if args.duration else None
        if remaining is not None and remaining <= 0:
            print(f"[supervisor] 时长已满（{args.duration}s），收工")
            return 0
        cmd = [sys.executable, os.path.join(REPO_ROOT, "tools", "run_engine.py")]
        if args.smoke:
            cmd.append("--smoke")
        if remaining is not None:
            cmd += ["--duration", str(int(remaining))]
        print(f"[supervisor] 启动引擎: {' '.join(cmd[1:])} (restarts={restarts})")
        try:
            code = subprocess.call(cmd, cwd=REPO_ROOT)
        except KeyboardInterrupt:
            print("[supervisor] 收到停止信号，退出")
            return 0
        if code == 0:
            print("[supervisor] 引擎正常退出，收工")
            return 0
        restarts += 1
        if restarts > args.max_restarts:
            print(f"[supervisor] ❌ 连续异常退出 {restarts} 次超过上限，放弃（人工检查"
                  f" logs/engine.log）")
            return 1
        print(f"[supervisor] 引擎异常退出 code={code}，{backoff}s 后第 {restarts} 次重启")
        time.sleep(backoff)
        backoff = min(600, backoff * 2)


if __name__ == "__main__":
    raise SystemExit(main())
