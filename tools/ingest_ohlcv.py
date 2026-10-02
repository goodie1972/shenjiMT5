"""tools/ingest_ohlcv.py — T0.7 数据入库 CLI。

连接运行中的 MT5 终端，把 M1~W1 各周期历史拉入 L1 权威库（UTC 秒，幂等 upsert）。
末根 forming bar 丢弃。可重复运行（增量效果来自 PK 幂等）。

用法：
  python tools/ingest_ohlcv.py                    # 全部周期，每周期最多 10 万根
  python tools/ingest_ohlcv.py --tfs M15,H1 --count 5000
"""

from __future__ import annotations

import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from config import settings
from config.settings import local_dt
from core.mt5_client import MT5Client
from data import database as db
from engine import data_factory


def main() -> int:
    parser = argparse.ArgumentParser(description="MT5 → SQLite ohlcv 入库")
    parser.add_argument("--tfs", default=",".join(settings.TIMEFRAMES),
                        help="逗号分隔周期（默认全部）")
    parser.add_argument("--pages", type=int, default=3,
                        help="每周期分页回填页数（每页 ≤99999 根）")
    parser.add_argument("--symbol", default=settings.SYMBOL)
    args = parser.parse_args()

    client = MT5Client()
    info = client.connect()
    spec = client.symbol_spec(args.symbol)
    print(f"终端已连接: login={info['login']} server={info['server']} "
          f"mode={info['margin_mode_name']} | {args.symbol} digits={spec['digits']} "
          f"pip={spec['pip_size']}")
    offset = client.server_offset_sec
    print(f"server offset: {offset / 3600:+.2f}h（UTC 秒入库）")

    db.init_db()
    tfs = [tf.strip().upper() for tf in args.tfs.split(",") if tf.strip()]
    print(f"\n{'TF':<5}{'入库根数':>10}  {'首 bar (UTC+8)':<18}{'末 bar (UTC+8)'}")
    print("-" * 70)
    ro = db.readonly_connect()
    for tf in tfs:
        try:
            n = data_factory.backfill(client, tf, max_pages=args.pages)
            row = ro.execute("SELECT MIN(timestamp), MAX(timestamp), COUNT(*) FROM ohlcv"
                             " WHERE timeframe=?", (tf,)).fetchone()
            first_ts, last_ts, total_rows = row[0], row[1], row[2]
            if first_ts is None:
                print(f"{tf:<5}{n:>10}  （空）")
                continue
            print(f"{tf:<5}{n:>10}  {local_dt(first_ts).strftime('%Y-%m-%d %H:%M'):<18}"
                  f"{local_dt(last_ts).strftime('%Y-%m-%d %H:%M')}  (库内累计 {total_rows})")
        except Exception as e:
            print(f"{tf:<5}  ❌ {e}")
    ro.close()
    client.shutdown()
    print(f"\n入库完成 → {settings.DB_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
