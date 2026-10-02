"""tools/clean_ohlcv.py — L3 清洗三规则（contract_data §6，方法论照搬旧库 clean v2）。

以 M1 为源聚合重算目标 TF，三规则：
  1. ghost 删除   — 目标 bar 存在但其桶内零 M1 覆盖（TF_GHOST_POLICY 可按 TF 保留）
  2. 偏差重建     — 聚合重算与现存 bar 偏差 > 阈值（close 或 ohlc 最大偏差）→ 以聚合结果重建
  3. 反向补洞     — M1 覆盖的桶在目标 TF 缺失 → 补插

评估窗口 = M1 覆盖范围；窗口外的目标 bar 原样透传（报告中单列 unassessed）。
安全边界：源库只读；只写 ohlcv_clean 表与 data/clean/ parquet，永不碰 ohlcv 表；
默认 dry-run，--apply 才落盘。

用法：
  python tools/clean_ohlcv.py                       # dry-run 报告
  python tools/clean_ohlcv.py --apply               # 产出 ohlcv_clean + clean parquet
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter, defaultdict

import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from config import settings
from config.settings import TF_SECONDS
from data import database as db

# 旧库 TF_GHOST_POLICY：H1/M15/M30 ghost=delete；H4 ghost=keep（唯一断档期数据）
TF_GHOST_POLICY = {"M15": "delete", "M30": "delete", "H1": "delete", "H4": "keep"}
FORBIDDEN_TABLES = ("ohlcv",)          # 硬边界：清洗产物绝不写这些表
CLEAN_TABLE = "ohlcv_clean"
DEV_THRESHOLD = 0.005                  # 0.5%


def detect_offset(ts: list[int], step: int) -> tuple[int, float]:
    """桶偏移众数探测（contract_data §4）。"""
    counts = Counter(t % step for t in ts)
    off, n = counts.most_common(1)[0]
    return off, n / len(ts) if ts else 0.0


def bucket_of(ts: int, step: int, offset: int) -> int:
    return ((ts - offset) // step) * step + offset


def aggregate_m1(m1: pd.DataFrame, step: int, offset: int) -> pd.DataFrame:
    """M1 → 目标 TF 桶聚合（open=首, high=max, low=min, close=末, volume=sum）。"""
    g = m1.assign(bucket=m1["time"].map(lambda t: bucket_of(t, step, offset)))
    agg = g.groupby("bucket").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last"), volume=("volume", "sum"))
    return agg.reset_index().rename(columns={"bucket": "time"})


def dev_ratio(a: pd.Series, b: pd.Series) -> float:
    """聚合值 vs 现存值最大相对偏差（防 0 除）。"""
    denom = b.abs().clip(lower=1e-9)
    return float(((a - b).abs() / denom).max())


def assess_tf(tgt: pd.DataFrame, agg: pd.DataFrame, step: int,
              m1_start: int, m1_end: int, threshold: float, metric: str,
              policy: str) -> dict:
    """单 TF 三规则评估（只在完整闭合桶内：桶起点 ≥ M1 起点且桶终点 ≤ M1 终点+1 根）。

    返回 ghosts/rebuilds 时间戳列表、fills 数量、清洗后的 final DataFrame。
    """
    agg_by_time = agg.set_index("time")
    covered = set(agg_by_time.index)
    tgt_by_time = tgt.set_index("time")
    closed = tgt[(tgt["time"] >= m1_start) & (tgt["time"] + step <= m1_end + 60)]

    ghosts, rebuilds = [], []
    cols = ["close"] if metric == "close" else ["open", "high", "low", "close"]
    for ts, row in closed.set_index("time").iterrows():
        if ts not in covered:
            ghosts.append(int(ts))                       # 规则1
            continue
        if dev_ratio(agg_by_time.loc[ts, cols], row[cols]) > threshold:
            rebuilds.append(int(ts))                     # 规则2
    fill_ts = sorted(t for t in covered                  # 规则3
                     if t not in tgt_by_time.index
                     and t >= m1_start and t + step <= m1_end + 60)

    final = tgt[~tgt["time"].isin(ghosts)] if policy == "delete" else tgt.copy()
    if rebuilds:
        final.loc[final["time"].isin(rebuilds),
                  ["open", "high", "low", "close", "volume"]] = \
            agg_by_time.loc[rebuilds, ["open", "high", "low", "close", "volume"]].values
    if fill_ts:
        extra = agg_by_time.loc[fill_ts].reset_index()
        final = pd.concat([final, extra], ignore_index=True).sort_values("time")
    return {"ghosts": ghosts, "rebuilds": rebuilds, "fills": len(fill_ts),
            "closed_n": len(closed), "final": final}


def main() -> int:  # noqa: C901 — 报告逻辑集中，可读性优先
    parser = argparse.ArgumentParser(description="L1 ohlcv → L3 清洗（三规则）")
    parser.add_argument("--targets", default=",".join(TF_GHOST_POLICY))
    parser.add_argument("--dev-threshold", type=float, default=DEV_THRESHOLD)
    parser.add_argument("--dev-metric", choices=["close", "ohlc"], default="ohlc")
    parser.add_argument("--apply", action="store_true", help="默认 dry-run")
    args = parser.parse_args()

    targets = [tf.strip().upper() for tf in args.targets.split(",") if tf.strip()]
    for tf in targets:
        if TF_GHOST_POLICY.get(tf) is None:
            print(f"❌ {tf} 不在 TF_GHOST_POLICY，拒绝处理")
            return 1

    ro = db.readonly_connect()
    m1 = pd.DataFrame(ro.execute(
        "SELECT timestamp AS time, open, high, low, close, volume FROM ohlcv"
        " WHERE timeframe='M1' ORDER BY timestamp").fetchall(),
        columns=["time", "open", "high", "low", "close", "volume"])
    if m1.empty:
        print("❌ L1 无 M1 源数据")
        return 1
    m1_start, m1_end = int(m1["time"].iloc[0]), int(m1["time"].iloc[-1])
    print(f"M1 覆盖窗口: {m1_start} ~ {m1_end}（{len(m1)} 根）"
          f" | 评估窗口外的目标 bar 将原样透传\n")

    results = {}
    for tf in targets:
        step = TF_SECONDS[tf]
        tgt = pd.DataFrame(ro.execute(
            f"SELECT timestamp AS time, open, high, low, close, volume FROM ohlcv"
            f" WHERE timeframe=? ORDER BY timestamp", (tf,)).fetchall(),
            columns=["time", "open", "high", "low", "close", "volume"])
        if tgt.empty:
            print(f"{tf}: 目标 TF 无数据，跳过")
            continue
        offset, ratio = detect_offset(list(tgt["time"]), step)
        if ratio < 0.95:
            print(f"{tf}: ⚠️ 桶偏移一致率 {ratio:.1%} < 95%，中止该 TF")
            continue

        assessment = assess_tf(tgt, aggregate_m1(m1, step, offset), step,
                               m1_start, m1_end, args.dev_threshold,
                               args.dev_metric, TF_GHOST_POLICY[tf])
        ghosts, rebuilds, fills = assessment["ghosts"], assessment["rebuilds"], assessment["fills"]
        final = assessment["final"]
        in_window = assessment["closed_n"]
        out_window = len(tgt) - in_window
        policy = TF_GHOST_POLICY[tf]

        results[tf] = dict(offset=offset, ratio=ratio, total=len(tgt),
                           in_window=in_window, unassessed=out_window,
                           ghosts=len(ghosts), ghost_kept=policy == "keep",
                           rebuilds=len(rebuilds), fills=fills, final=final)
        print(f"{tf}: 桶偏移={offset}s(一致率 {ratio:.0%}) | 闭合桶内 {in_window}"
              f" / 透传 {out_window} | ghost {len(ghosts)}"
              f"({'删除' if policy == 'delete' else '保留'}) | 重建 {len(rebuilds)}"
              f" | 补洞 {fills}")

    ro.close()

    if not args.apply:
        print("\n[dry-run] 未写任何数据；确认后加 --apply 落盘")
        return 0

    # ── 落盘：ohlcv_clean 表 + data/clean/ parquet ──
    for tf in TF_GHOST_POLICY:
        if tf not in results:
            continue
        final = results[tf]["final"]
        conn = db.connect()
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {CLEAN_TABLE} ("
            "timeframe TEXT NOT NULL, timestamp INTEGER NOT NULL, open REAL NOT NULL,"
            " high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL, volume REAL NOT NULL,"
            " PRIMARY KEY (timeframe, timestamp))")
        conn.executemany(
            f"INSERT OR REPLACE INTO {CLEAN_TABLE}"
            " (timeframe, timestamp, open, high, low, close, volume) VALUES (?,?,?,?,?,?,?)",
            [(tf, int(r.time), float(r.open), float(r.high), float(r.low),
              float(r.close), float(r.volume)) for r in final.itertuples()])
        conn.commit()
        conn.close()
        os.makedirs(settings.CLEAN_DIR, exist_ok=True)
        out = pd.DataFrame({"time": final["time"].astype("int64"),
                            "open": final["open"], "high": final["high"],
                            "low": final["low"], "close": final["close"],
                            "volume": final["volume"]})
        out.to_parquet(os.path.join(settings.CLEAN_DIR, f"{settings.SYMBOL}_{tf}_clean.parquet"),
                       index=False)
        print(f"  {tf}: ohlcv_clean {len(final)} 行 + parquet 已写")
    print(f"\n[apply] 完成 → {CLEAN_TABLE} 表 + {settings.CLEAN_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
