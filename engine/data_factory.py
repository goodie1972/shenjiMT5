"""engine/data_factory.py — 轨道1：rates → UTC 入库 + bar0/bar1 供给。

契约依据：docs/contracts/contract_data.md §2/§7。
- copy_rates 末根 = forming bar（bar0）：**入库与指标一律丢弃它**（INV-S1），
  仅实时缓存的 candles[-1] 保留给价格触发。
- 入库前必须经 client.to_utc()（D1：库内不允许 server time）。
"""

from __future__ import annotations

import logging
from typing import Optional

from config import settings
from data import database as db
from strategies.base import Candle

logger = logging.getLogger(__name__)


def rows_to_utc(rows: list[dict], client) -> list[dict]:
    """client.copy_rates 的 server-time 行 → UTC 行（丢 forming bar 在调用方做）。"""
    out = []
    for r in rows:
        out.append({
            "timestamp": client.to_utc(r["time"]),
            "open": r["open"], "high": r["high"], "low": r["low"],
            "close": r["close"], "volume": r["volume"],
        })
    return out


def pull_timeframe(client, timeframe: str, count: int,
                   db_path: str = settings.DB_PATH) -> int:
    """单页拉取并入库（幂等 upsert）。多拉 1 根用于砍尾 forming bar。

    Returns: 实际入库行数。
    """
    from core.mt5_client import MAX_COPY_COUNT
    rows = client.copy_rates(settings.SYMBOL, timeframe,
                             min(count + 1, MAX_COPY_COUNT))
    if rows:
        rows = rows[:-1]                     # forming bar 不入库（contract_data §7）
    utc_rows = rows_to_utc(rows, client)
    n = db.upsert_candles(timeframe, utc_rows, db_path=db_path)
    logger.info("[data_factory] %s pulled=%d stored=%d", timeframe, len(utc_rows), n)
    return len(utc_rows)


def backfill(client, timeframe: str, max_pages: int = 3,
             page_size: int = None,
             db_path: str = settings.DB_PATH) -> int:
    """分页历史回填：首页含 forming bar（砍尾），之后按 start_pos 向历史翻页，
    直到终端给不满一页（历史耗尽）或达到页数上限。

    max_pages=3 × 99999 ≈ M1 半年 / H1 十几年 / D1 全部（实测 MetaQuotes-Demo）。
    """
    from core.mt5_client import MAX_COPY_COUNT
    page = page_size or MAX_COPY_COUNT
    stored, start_pos = 0, 0
    for page_no in range(max_pages):
        rows = client.copy_rates(settings.SYMBOL, timeframe, page, start_pos=start_pos)
        if not rows:
            break
        exhausted = len(rows) < page
        if start_pos == 0:
            rows = rows[:-1]                 # 首页末根 = forming bar
        stored += db.upsert_candles(timeframe, rows_to_utc(rows, client),
                                    db_path=db_path)
        logger.info("[backfill] %s page%d start=%d rows=%d exhausted=%s",
                    timeframe, page_no, start_pos, len(rows), exhausted)
        if exhausted:
            break
        start_pos += page
    return stored


def build_cache(client, timeframe: str, lookback: int = 600,
                db_path: str = settings.DB_PATH) -> dict:
    """策略数据源（DataProvider 形状，T1.2 起含指标）。

    - candles：闭合序列（来自 L1，UTC）+ 末尾拼上 forming bar（来自终端），
      即 [-1]=bar0(forming，仅价格触发)、[-2]=bar1（INV-S1/契约 §7）。
    - indicators：本地指标引擎的 bar1 值（engine/indicators.py），
      并把快照写入 indicator_snapshots（供 get_indicator_series / M2 对齐）。
    """
    import pandas as pd

    from engine import indicators

    rows = db.get_candles(timeframe, limit=lookback, db_path=db_path,
                          order="DESC")[::-1]      # 最新 lookback 根，还原升序
    if not rows:
        return {"candles": [], "indicators": {}}
    df = pd.DataFrame(rows).rename(columns={"timestamp": "time"})
    indicators_kv = indicators.compute_bar1(df)

    bar1_ts = int(df["time"].iloc[-1])
    db.upsert_indicator_snapshots(timeframe, bar1_ts, indicators_kv, db_path=db_path)

    candles = [Candle(time=int(r.time), open=float(r.open), high=float(r.high),
                      low=float(r.low), close=float(r.close), volume=float(r.volume))
               for r in df.itertuples()]
    forming = client.copy_rates(settings.SYMBOL, timeframe, 1)
    if forming:
        f = forming[-1]
        candles.append(Candle(time=client.to_utc(f["time"]), open=f["open"],
                              high=f["high"], low=f["low"], close=f["close"],
                              volume=f["volume"]))
    return {"candles": candles, "indicators": indicators_kv}


def sync_all(client, timeframes: Optional[list[str]] = None, count: int = 300,
             db_path: str = settings.DB_PATH) -> dict[str, int]:
    """实时循环入口（M1 接线）：各 TF 拉最新并入库。"""
    tfs = timeframes or settings.TIMEFRAMES
    return {tf: pull_timeframe(client, tf, count, db_path=db_path) for tf in tfs}
