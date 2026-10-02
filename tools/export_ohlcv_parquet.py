"""tools/export_ohlcv_parquet.py — L2 研究层唯一生产者（contract_data §5）。

L1 SQLite → parquet，单向全量重写式导出：dedupe → sort → validate → 写文件 → manifest。
用法：python tools/export_ohlcv_parquet.py [--tfs H1,H4]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time

import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from config import settings
from data import database as db
from data.parquet_store import COLUMNS, _manifest_path, _path

MAX_ROWS = 1_000_000


def export_timeframe(symbol: str, timeframe: str) -> dict:
    rows = db.get_candles(timeframe, limit=MAX_ROWS, db_path=settings.DB_PATH)
    if not rows:
        raise ValueError(f"{timeframe}: L1 无数据")
    df = pd.DataFrame(rows).rename(columns={"timestamp": "time"})
    df = df[COLUMNS]
    df["time"] = df["time"].astype("int64")
    for c in COLUMNS[1:]:
        df[c] = df[c].astype("float64")
    # validate：时间单调、无重复、无 NaN
    df = df.drop_duplicates("time").sort_values("time").reset_index(drop=True)
    if df["time"].duplicated().any() or not df["time"].is_monotonic_increasing:
        raise ValueError(f"{timeframe}: 导出校验失败（重复/乱序）")
    if df[COLUMNS[1:]].isna().any().any():
        raise ValueError(f"{timeframe}: 存在 NaN")
    out = _path(symbol, timeframe)
    os.makedirs(settings.PARQUET_DIR, exist_ok=True)
    df.to_parquet(out, index=False)
    return {"rows": len(df), "first": int(df["time"].iloc[0]),
            "last": int(df["time"].iloc[-1]), "written_at": time.time(),
            "sha256": _sha256(out)}


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="L1 → L2 研究层导出")
    parser.add_argument("--symbol", default=settings.SYMBOL)
    parser.add_argument("--tfs", default=",".join(settings.TIMEFRAMES))
    args = parser.parse_args()

    tfs = [tf.strip().upper() for tf in args.tfs.split(",") if tf.strip()]
    manifest_path = _manifest_path()
    manifest = {"files": {}}
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)

    print(f"{'TF':<5}{'行数':>10}  首 bar (UTC)        末 bar (UTC)        sha256[:12]")
    print("-" * 86)
    for tf in tfs:
        try:
            info = export_timeframe(args.symbol, tf)
            key = f"{args.symbol}_{tf}.parquet"
            manifest["files"][key] = info
            f_str = time.strftime("%Y-%m-%d %H:%M", time.gmtime(info["first"]))
            l_str = time.strftime("%Y-%m-%d %H:%M", time.gmtime(info["last"]))
            print(f"{tf:<5}{info['rows']:>10}  {f_str:<20}{l_str:<20}{info['sha256'][:12]}")
        except Exception as e:
            print(f"{tf:<5}  ❌ {e}")

    os.makedirs(settings.PARQUET_DIR, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"\nmanifest → {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
