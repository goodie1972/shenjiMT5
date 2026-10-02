"""strategies/scanner.py — 策略自动发现。

纪律照搬旧库 scanner v4：目录签名（文件名+mtime）失效才重扫；取首个 BaseStrategy
子类；重名告警并跳过。 excluded：base/scanner/__init__。
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import os
import sys
import threading

from strategies.base import BaseStrategy

logger = logging.getLogger(__name__)

_EXCLUDED_FILES = {"__init__.py", "base.py", "scanner.py", "followave_core.py"}

_lock = threading.RLock()
_cache: dict[str, type[BaseStrategy]] = {}
_dir_signature: Optional[str] = None


def _strategies_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _calc_dir_signature() -> str:
    entries = []
    for fn in sorted(os.listdir(_strategies_dir())):
        if fn.endswith(".py") and fn not in _EXCLUDED_FILES:
            p = os.path.join(_strategies_dir(), fn)
            entries.append(f"{fn}:{os.path.getmtime(p)}")
    return "|".join(entries)


def _scan_unlocked() -> dict[str, type[BaseStrategy]]:
    global _dir_signature
    found: dict[str, type[BaseStrategy]] = {}
    for fn in sorted(os.listdir(_strategies_dir())):
        if not fn.endswith(".py") or fn in _EXCLUDED_FILES:
            continue
        mod_name = fn[:-3]
        spec = importlib.util.spec_from_file_location(
            f"strategies.{mod_name}", os.path.join(_strategies_dir(), fn))
        if spec is None or spec.loader is None:
            continue
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        try:
            spec.loader.exec_module(mod)
        except Exception:
            logger.exception("[scanner] 加载失败，跳过: %s", fn)
            continue
        for attr in vars(mod).values():
            if (isinstance(attr, type) and issubclass(attr, BaseStrategy)
                    and attr is not BaseStrategy and getattr(attr, "name", "base") != "base"):
                name = attr.name
                if name in found:
                    logger.warning("[scanner] 策略重名 '%s'（%s），跳过后者", name, fn)
                else:
                    found[name] = attr
                break  # 每文件只取首个子类（旧库纪律）
    _dir_signature = _calc_dir_signature()
    return found


def scan(force: bool = False) -> dict[str, type[BaseStrategy]]:
    """返回 {name: 策略类}。目录签名未变时走缓存。"""
    global _cache
    with _lock:
        sig = _calc_dir_signature()
        if force or sig != _dir_signature or not _cache:
            _cache = _scan_unlocked()
        return dict(_cache)


def create_strategies(pool: dict[str, dict],
                      data_provider) -> list[BaseStrategy]:
    """按策略池实例化。pool: {name: {magic, timeframe}}；0 magic 的池项视为禁用。"""
    classes = scan()
    instances: list[BaseStrategy] = []
    for name, cfg in pool.items():
        if cfg.get("magic", 0) == 0:
            logger.info("[scanner] %s magic=0 → 禁用", name)
            continue
        cls = classes.get(name)
        if cls is None:
            logger.warning("[scanner] 池内策略未找到: %s", name)
            continue
        instances.append(cls(magic=cfg["magic"], timeframe=cfg["timeframe"],
                             data_provider=data_provider))
    return instances
