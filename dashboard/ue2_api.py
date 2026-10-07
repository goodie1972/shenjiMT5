"""dashboard/ue2_api.py — U-E2 端点：运行配置 / 引擎控制 / 策略中心。

- /api/config*：运行配置（data/runtime_config.json，键值白名单存储）
- /api/engine/start|stop|restart：面板进程对引擎进程的控制（subprocess）
- /api/strategies/*：策略发现（scanner）+ 池编辑 + 下架到 backup/
响应形状以旧后端为准（前端零改动优先）。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import inspect
import threading

from fastapi import APIRouter, HTTPException

from config import settings

router = APIRouter(prefix="/api")

CFG_PATH = os.path.join(settings.DATA_DIR, "runtime_config.json")
REPO_ROOT = settings.REPO_ROOT

DEFAULTS: dict = {
    # 风控（ConfigView RiskConfig 编辑键）
    "lot_size": 0.01,
    "max_positions_live": 1,
    "max_positions_paper": 5,
    "default_sl": 50,
    "default_tp": 100,
    "slippage": 30,
    "tp_cooldown": 2,
    "abs_loss_limit": 30,
    "max_daily_loss_pct": 12.0,
    "floating_warn_pct": 5.0,
    "floating_block_pct": 10.0,
    "rapid_exit_window": 300,
    "max_rapid_exits": 3,
    "rapid_exit_cooldown": 7200,
    "consec_loss_limit": 3,
    "consec_loss_cooldown": 4,
    "min_hold_seconds": 30,
    # 通用
    "engine_mode": "demo",
}

_cfg_lock = threading.Lock()


def _load() -> dict:
    if not os.path.exists(CFG_PATH):
        return {"risk": dict(DEFAULTS), "paper": {}, "strategy_pool": {}, "coordinator": {}}
    with open(CFG_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save(cfg: dict) -> None:
    os.makedirs(settings.DATA_DIR, exist_ok=True)
    tmp = CFG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CFG_PATH)


def _risk_flat(cfg: dict) -> dict:
    risk = dict(DEFAULTS)
    risk.update(cfg.get("risk", {}))
    return risk


# ── 运行配置 ─────────────────────────────────────────────────
@router.get("/config")
def api_config():
    """完整运行时配置（旧库契约：扁平风控键 + strategy_pool + coordinator
    + paper_trading + symbol）。前端 store 直接读 items.strategy_pool 等。"""
    with _cfg_lock:
        cfg = _load()
        out = _risk_flat(cfg)
        out["strategy_pool"] = cfg.get("strategy_pool", {})
        out["coordinator"] = cfg.get("coordinator", {"enabled": False})
        out["paper_trading"] = {"enabled": False, "max_positions": None,
                                "ignore_gates": False, "initial_balance": 0,
                                "lot_size": None, **cfg.get("paper", {})}
        out["symbol"] = getattr(settings, "SYMBOL", "XAUUSD")
        return out


@router.post("/config")
def api_config_update(body: dict):
    updates = body.get("updates") or {}
    if not isinstance(updates, dict):
        raise HTTPException(422, "updates 必须是对象")
    with _cfg_lock:
        cfg = _load()
        risk = cfg.setdefault("risk", {})
        for k, v in updates.items():
            if k not in DEFAULTS:
                continue                                  # 白名单外丢弃
            try:
                risk[k] = float(v) if "." in str(v) or isinstance(v, float) else int(float(v))
            except (TypeError, ValueError):
                risk[k] = v
        _save(cfg)
    return {"ok": True, "config": _risk_flat(cfg)}


@router.post("/config/reset")
def api_config_reset(body: dict):
    key = (body or {}).get("key")
    with _cfg_lock:
        cfg = _load()
        if key:
            cfg.get("risk", {}).pop(key, None)
        else:
            cfg["risk"] = dict(DEFAULTS)
        _save(cfg)
    return {"ok": True, "config": _risk_flat(cfg)}


@router.get("/config/strategy-pool")
def api_strategy_pool():
    with _cfg_lock:
        return _load().get("strategy_pool", {})


@router.post("/config/strategy-pool")
def api_strategy_pool_update(body: dict):
    pool = (body or {}).get("pool") or {}
    if not isinstance(pool, dict):
        raise HTTPException(422, "pool 必须是对象")
    with _cfg_lock:
        cfg = _load()
        cfg["strategy_pool"] = pool
        _save(cfg)
    return {"ok": True}


@router.get("/config/coordinator")
def api_coordinator():
    with _cfg_lock:
        return _load().get("coordinator", {"enabled": False})


@router.post("/config/coordinator")
def api_coordinator_update(body: dict):
    cfg_new = (body or {}).get("config") or {}
    with _cfg_lock:
        cfg = _load()
        cfg["coordinator"] = cfg_new
        _save(cfg)
    return {"ok": True}


@router.get("/config/paper")
def api_paper():
    with _cfg_lock:
        p = _load().get("paper", {})
    return {"enabled": False, "max_positions": None, "ignore_gates": False,
            "initial_balance": 0, "lot_size": None, **p}


@router.post("/config/paper")
def api_paper_update(body: dict):
    cfg_new = (body or {}).get("config") or {}
    with _cfg_lock:
        cfg = _load()
        cfg["paper"] = {**cfg.get("paper", {}), **cfg_new}
        _save(cfg)
    return {"ok": True, "config": cfg["paper"], "mode_switch": True}


@router.post("/paper-trading/reset")
def api_paper_reset():
    return {"ok": True, "note": "本地纸面模式未启用（D4）；demo 账户历史请用终端管理"}


# ── 引擎控制（面板进程 → 引擎进程）───────────────────────────
_PS_KILL = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
            "Where-Object { $_.CommandLine -match 'run_engine|supervise_engine' } | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }")
_PS_COUNT = _PS_KILL.replace("Stop-Process -Id $_.ProcessId -Force", "Measure-Object | Select-Object -ExpandProperty Count")


def _engine_running() -> bool:
    r = subprocess.run(["powershell", "-NoProfile", "-Command", _PS_COUNT],
                       capture_output=True, text=True, timeout=30)
    try:
        return int(r.stdout.strip() or 0) > 0
    except ValueError:
        return False


@router.post("/engine/start")
def api_engine_start():
    if _engine_running():
        return {"ok": True, "note": "引擎已在运行"}
    subprocess.Popen(
        [sys.executable, os.path.join("tools", "supervise_engine.py"), "--smoke",
         "--followave", "--duration", "1209600"],
        cwd=settings.REPO_ROOT,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    return {"ok": True}


@router.post("/engine/stop")
def api_engine_stop():
    subprocess.run(["powershell", "-NoProfile", "-Command", _PS_KILL],
                   capture_output=True, text=True, timeout=60)
    return {"ok": True}


HEARTBEAT_MAX_AGE = 120  # 秒；心跳超过此龄视为引擎离线（tick 周期 1s，冗余充足）


@router.post("/engine/restart")
def api_engine_restart():
    api_engine_stop()
    import time
    time.sleep(3)
    return api_engine_start()


@router.get("/engine/strategies")
def api_engine_strategies():
    """引擎运行中的策略（旧库契约形状：running=对象数组 + available=名单）。

    真源 = 引擎心跳文件（engine 每 tick 写入 ts+strategies）；心跳缺失或
    过期 → 引擎离线，running 如实返回空数组，不拿配置启用冒充在线。
    前端消费 running[].name（策略中心"运行中"标签 / 交易终端面板）。
    """
    running: list = []
    hb = os.path.join(settings.LOG_DIR, "heartbeat.txt")
    try:
        with open(hb, encoding="utf-8") as f:
            data = json.load(f)
        # 兼容历史格式：旧心跳是纯时间戳整数（json.load 出 int）→ 视为离线
        if isinstance(data, dict) and \
                settings.utc_now() - int(data.get("ts", 0)) <= HEARTBEAT_MAX_AGE:
            running = [s for s in (data.get("strategies") or [])
                       if isinstance(s, dict) and s.get("name")]
    except (OSError, TypeError, ValueError):
        pass
    try:
        sys.path.insert(0, settings.REPO_ROOT)
        from strategies import scanner
        available = sorted(scanner.scan().keys())
    except Exception:
        available = []
    return {"running": running, "available": available}


try:
    import psutil  # noqa: E402
except ImportError:
    psutil = None  # type: ignore


# ── 策略中心 ─────────────────────────────────────────────────
@router.get("/strategies/available")
def api_strategies_available():
    sys.path.insert(0, settings.REPO_ROOT)
    from strategies import scanner
    classes = scanner.scan(force=True)
    with _cfg_lock:
        cfg = _load()
    pool = cfg.get("strategy_pool", {})
    # 系统交易模式（纸面=demo / 实盘=live）唯一来源：risk.engine_mode。
    # 策略不再有独立 mode（旧字段已移除），一律跟随系统。
    engine_mode = _risk_flat(cfg).get("engine_mode", "demo")
    out = []
    for name, cls in sorted(classes.items()):
        mod = sys.modules[cls.__module__]
        version = getattr(mod, "STRATEGY_VERSION", "")
        magic = getattr(mod, "STRATEGY_MAGIC", 0)
        pool_cfg = pool.get(name, {})
        out.append({
            "id": name,                                # 池键 = 策略名（旧库同款）
            "name": name, "default_magic": int(magic),
            "magic": int(pool_cfg.get("magic", magic) or magic),
            "timeframe": pool_cfg.get("timeframe", getattr(cls, "TIMEFRAME", "M30")),
            "version": version,
            "enabled": pool_cfg.get("enabled", False),  # 池真源 = runtime_config
            "mode": engine_mode,                        # 跟随系统（契约兼容保留键）
            "max_positions": pool_cfg.get("max_positions", 1),
            "double_first": pool_cfg.get("double_first", False),
            "file": os.path.basename(inspect.getfile(cls)),
        })
    return {"strategies": out, "engine_mode": engine_mode}


@router.post("/strategies/batch-remove")
def api_strategies_batch_remove(body: dict):
    """下架策略：.py + 双语文档移入 strategies/backup/，池中移除（重启生效）。"""
    names = (body or {}).get("names") or []
    if not names:
        raise HTTPException(422, "names 为空")
    sys.path.insert(0, settings.REPO_ROOT)
    from strategies import scanner
    classes = scanner.scan(force=True)
    moved, errors = [], []
    backup = os.path.join(settings.REPO_ROOT, "strategies", "backup")
    os.makedirs(backup, exist_ok=True)
    for name in names:
        cls = classes.get(name)
        if cls is None:
            errors.append(f"{name}: 未发现")
            continue
        stem = cls.__module__.rsplit(".", 1)[-1]
        for cand in (stem + ".py", stem + "_cn.md", stem + "_en.md"):
            srcf = os.path.join(settings.REPO_ROOT, "strategies", cand)
            if os.path.exists(srcf):
                shutil.move(srcf, os.path.join(backup, cand))
                moved.append(cand)
    with _cfg_lock:
        cfg = _load()
        pool = cfg.get("strategy_pool", {})
        for name in names:
            pool.pop(name, None)
        cfg["strategy_pool"] = pool
        _save(cfg)
    return {"ok": True, "moved": moved, "errors": errors}


@router.get("/strategies/logics")
def api_strategies_logics():
    """进出场逻辑表（旧库从 md 解析）——占位：返回空表，前端渲染空逻辑面板。"""
    return {}
