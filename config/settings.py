"""神机 MT5 版 — 全局配置与风控参数。

纪律：
- 风控参数值 = docs/contracts/contract_risk.md §2 锁定值。改值必须先改契约，再改这里的测试，最后改这里。
- 时间纪律（D1）：存储一律 UTC 秒 int64；显示用 UTC+8；禁止裸 datetime.fromtimestamp()/datetime.now()。
"""

import os
import time
from datetime import datetime, timezone, timedelta

# ── 品种与周期 ────────────────────────────────────────────────
SYMBOL = "XAUUSD"
LOT_SIZE = 0.01             # 默认下单手数（取 symbol spec volume_min/step 校验）
DEVIATION = 30              # 最大滑点（points，下单/平仓共用）
TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1"]
TF_SECONDS = {
    "M1": 60, "M5": 300, "M15": 900, "M30": 1800,
    "H1": 3600, "H4": 14400, "D1": 86400, "W1": 604800,
}

# ── 路径 ─────────────────────────────────────────────────────
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, "data")
DB_PATH = os.path.join(DATA_DIR, "market_data.db")
JOURNAL_DIR = os.path.join(DATA_DIR, "journal")
PARQUET_DIR = os.path.join(DATA_DIR, "am_parquet")
CLEAN_DIR = os.path.join(DATA_DIR, "clean")
LOG_DIR = os.path.join(REPO_ROOT, "logs")
SAFETY_LOCK_PATH = os.path.join(REPO_ROOT, "config", "safety_lock.txt")
SERVER_OFFSET_PATH = os.path.join(DATA_DIR, "server_offset.json")

# ── 时区（D1：只用于显示层）──────────────────────────────────
LOCAL_TZ = timezone(timedelta(hours=8))
_UTC = timezone.utc


def utc_now() -> float:
    """当前 UTC Unix 秒。全库唯一取"现在"的入口。"""
    return time.time()


def utc_dt(ts: float) -> datetime:
    """UTC 秒 → tz-aware UTC datetime（展示/调试用，不用于计算"现在"）。"""
    return datetime.fromtimestamp(ts, tz=_UTC)


def local_dt(ts: float) -> datetime:
    """UTC 秒 → UTC+8 显示时间。仅渲染层使用，禁止回写存储。"""
    return datetime.fromtimestamp(ts, tz=LOCAL_TZ)


# ── 风控参数（contract_risk.md §2 锁定值，勿在此直接改值）────
RISK_PARAMS = {
    "max_daily_loss_pct":                12.0,
    "per_strategy_max_positions":        1,
    "floating_loss_warn_pct":            5.0,
    "floating_loss_block_pct":           10.0,
    "per_strategy_realized_loss_pct":    5.0,
    "per_strategy_loss_block_hours":     12,
    "per_strategy_realized_loss_amount": 30.0,   # realized_pnl <= -30.0 触发
    "max_consecutive_losses":            3,
    "consecutive_loss_cooldown_hours":   4,
    "max_rapid_exits":                   3,
    "rapid_exit_window_seconds":         300,
    "rapid_exit_cooldown_seconds":       7200,
    "profit_exit_cooldown_hours":        2,
    "min_hold_seconds":                  30,     # 疑似快速平仓自动锁
    "same_dir_float_loss_block":         0.5,    # 同向浮亏禁加仓阈值
    "news_before_minutes":               30,
    "news_after_minutes":                120,
    "news_bias_adx_gate":                25,
    "news_bias_di_gap":                  8,
    "position_gate_m30_lookback":        40,
    "position_gate_bottom":              0.10,
    "position_gate_top":                 0.90,
    "di_gate_skip_threshold":            20,
    "rally_drop_lookback":               30,
    "rally_drop_threshold":              1.5,
    "rally_drop_adx_skip":               25,
}

# ── 引擎参数 ─────────────────────────────────────────────────
STRATEGY_WORKERS = 4          # 策略线程池并发（旧库同规模）
ATHLETE_MAX_TICKS = 3         # ticket 复核窗口（G15）
FALLBACK_SL_ATR_MULT = 2.0    # 策略未给 SL 时的兜底
FALLBACK_TP_ATR_MULT = 4.0
MIN_CANDLES_FOR_SIGNAL = 10   # on_tick 最少 K 线守卫
INDICATOR_LOOKBACK = 600      # 指标计算的闭合 bar 窗口（覆盖 ema_200）

# ── 门禁配置（值域见 contract_risk §1；G12 参数在 RISK_PARAMS）──
GLOBAL_DIRECTION_FILTER = "BOTH"      # BOTH | BUY_ONLY | SELL_ONLY（G13）
MTF_RESONANCE_ENABLED = False         # G14 MTF 共振（M1 默认关，实现后开）
NEWS_BIAS_BLOCK_ENABLED = False       # G2 新闻偏向封锁（数据源 M2 决策，默认关）
NEWS_CALENDAR_PROVIDER = None         # G1 新闻日历提供者：callable(now)->窗口终点 UTC 秒；
                                      # None = 未配置（放行并告警，非 fail-open——见 AGENTS §5.3 注）
MARKET_SUN_OPEN_HOUR_UTC = 21         # G5 市场时段近似（broker 可改）
MARKET_FRI_CLOSE_HOUR_UTC = 21
