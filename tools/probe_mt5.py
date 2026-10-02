"""tools/probe_mt5.py — M0 探测脚本（T0.5）。

一次探明 PRD 风险登记册的四个 MT5 地雷（R4~R7）+ 数据可用性：
  1. 环境层：MetaTrader5 包 / 64 位 Python / 终端连接
  2. 账户层：登录、交易权限、净持 vs 对冲（R4，PRD 决策 D5）
  3. 品种层：XAUUSD digits/point/filling/stops（R5，决策 D4/D6）
  4. 时区层：server offset 实测 + 各 TF 桶偏移众数探测（R6，决策 D1）
  5. 数据层：M1~D1 copy_rates 可用性、real ticks、deals 流水（R7）

输出：终端摘要 + docs/probe/mt5_probe_report.md（markdown 报告）。
每个探测段独立容错，失败段给出 checklist 提示。

用法：
  python tools/probe_mt5.py                     # 挂载已运行的终端
  python tools/probe_mt5.py --login 123 --password xxx --server Broker-Demo
  python tools/probe_mt5.py --path "C:/Program Files/MetaTrader 5/terminal64.exe"
"""

from __future__ import annotations

import argparse
import os
import platform
import sys
from collections import Counter
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from config import settings  # noqa: E402
from config.settings import TF_SECONDS  # noqa: E402

SYMBOL = settings.SYMBOL
REPORT_DIR = os.path.join(REPO_ROOT, "docs", "probe")
CHECKLIST = {
    "package": "pip install MetaTrader5（需 Windows + 64 位 Python）",
    "terminal": "启动 MetaTrader 5 终端并保持登录；勾选 工具→选项→EA 交易系统→允许算法交易",
    "account": "终端内登录 demo 账户（无账户：文件→开立模拟账户）",
    "symbol": "终端 市场报价 窗口右键 → 显示全部 / 符号，确认 XAUUSD 可见可交易",
    "rates": "终端 查看→符号→XAUUSD→柱形图，调大最大 K 线数（如 100000）",
    "deals": "demo 账户历史为空属正常；实盘对账能力在 M1 验证",
}


class Probe:
    def __init__(self):
        self.lines: list[str] = []
        self.failures: list[str] = []

    def section(self, title: str):
        self.lines += ["", f"## {title}", ""]

    def ok(self, label: str, value: str = ""):
        self.lines.append(f"- ✅ **{label}** {value}".rstrip())

    def warn(self, label: str, value: str = ""):
        self.lines.append(f"- ⚠️ **{label}** {value}".rstrip())

    def fail(self, label: str, err: str, hint: str | None = None):
        self.lines.append(f"- ❌ **{label}** {err}")
        self.failures.append(f"{label}: {err}")
        if hint:
            self.lines.append(f"  - 处理建议：{hint}")

    def kv(self, label: str, value):
        self.lines.append(f"- {label}: `{value}`")


def mode_of(ts_list: list[int], step: int) -> tuple[int | None, float]:
    """桶偏移众数探测（contract_data §4 方法论）：mode(ts % step) 与一致率。"""
    if not ts_list:
        return None, 0.0
    counts = Counter(t % step for t in ts_list)
    offset, n = counts.most_common(1)[0]
    return offset, n / len(ts_list)


def fmt_ts(ts: int | None) -> str:
    if not ts:
        return "-"
    return f"{ts} ({datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()} UTC)"


def probe_environment(p: Probe, mt5):
    p.section("1. 环境")
    p.ok("Python", f"{sys.version.split()[0]} {'64位' if platform.machine().endswith('64') else '⚠️ 非 64 位！'} {platform.system()}")
    p.kv("MetaTrader5 包版本", getattr(mt5, "__version__", "unknown"))


def probe_terminal(p: Probe, mt5, init_kwargs: dict) -> bool:
    p.section("2. 终端连接")
    if not mt5.initialize(**init_kwargs):
        p.fail("终端连接", str(mt5.last_error()), CHECKLIST["terminal"])
        return False
    ti = mt5.terminal_info()
    vi = mt5.version()
    p.ok("终端连接成功")
    if ti:
        p.kv("终端", f"{ti.name} build {ti.build} @ {ti.path}")
        p.kv("数据构建", ti.data_path)
        if ti.trade_allowed:
            p.ok("允许算法交易")
        else:
            p.warn("允许算法交易", "当前未勾选——下单会被拒（CHECKLIST: terminal）")
    p.kv("MT5 版本", f"{vi[0]} / {vi[1]}")
    return True


def probe_account(p: Probe, mt5) -> dict | None:
    p.section("3. 账户（R4：净持 vs 对冲）")
    acc = mt5.account_info()
    if acc is None:
        p.fail("账户信息", str(mt5.last_error()), CHECKLIST["account"])
        return None
    p.ok("账户登录", f"login={acc.login} server={acc.server} ({acc.currency})")
    p.kv("余额/净值", f"{acc.balance:.2f} / {acc.equity:.2f}")
    mm = int(acc.margin_mode)
    if mm == 2:
        p.ok("账户模式", "HEDGING（对冲）——与 MT4 语义一致，v1 门禁无需调整")
    elif mm == 1:
        p.warn("账户模式", "NETTING（净持）——v1 并发=1 下等价；放开并发前必须写 netting 语义附录（contract_strategy §7.2）")
    else:
        p.warn("账户模式", f"未知 margin_mode={mm}")
    if acc.trade_allowed:
        p.ok("账户允许交易")
    else:
        p.warn("账户允许交易", "invest 密码或账户权限问题（CHECKLIST: account）")
    return {"login": acc.login, "server": acc.server, "margin_mode": mm}


def probe_symbol(p: Probe, mt5) -> dict | None:
    p.section("4. 品种规约 XAUUSD（R5：digits/filling/stops）")
    if not mt5.symbol_select(SYMBOL, True):
        p.fail("品种选择", str(mt5.last_error()), CHECKLIST["symbol"])
        return None
    si = mt5.symbol_info(SYMBOL)
    if si is None:
        p.fail("品种信息", str(mt5.last_error()), CHECKLIST["symbol"])
        return None
    p.ok("品种可见", SYMBOL)
    p.kv("digits/point", f"{si.digits} / {si.point}")
    pip = si.point * (10 if si.digits >= 3 else 1)
    p.kv("pip_size（推导）", f"{pip}（旧库硬编码 0.01 的替代品，运行时取）")
    p.kv("tick_value/tick_size", f"{si.trade_tick_value} / {si.trade_tick_size}")
    p.kv("手数 min/step/max", f"{si.volume_min} / {si.volume_step} / {si.volume_max}")
    p.kv("stops_level/freeze_level", f"{si.trade_stops_level} / {si.trade_freeze_level}")
    p.kv("filling_mode 掩码", f"{si.filling_mode}（1=FOK 2=IOC 4=RETURN，下单按位自适应）")
    p.kv("trade_mode", f"{si.trade_mode}（4=full）")
    if si.digits >= 3:
        p.warn("digits ≥ 3", "与旧库 2 位报价不同——回测口径与 SL/TP 距离需按 pip_size 换算")
    return {"digits": si.digits, "point": si.point, "pip_size": pip}


def probe_timezone(p: Probe, mt5) -> float | None:
    p.section("5. 时区（R6：server offset 实测 + 桶偏移）")
    t = mt5.symbol_info_tick(SYMBOL)
    if t is None or not t.time:
        p.fail("tick", str(mt5.last_error()), CHECKLIST["symbol"])
        return None
    now_utc = datetime.now(tz=timezone.utc).timestamp()
    offset = float(t.time - now_utc)
    p.ok("server offset（实测）", f"{offset / 3600:+.2f}h（tick.time={fmt_ts(t.time)}）")
    if abs(offset / 3600 - round(offset / 3600)) > 0.05:
        p.warn("非整小时偏移", "含分钟级成分——与旧库 MT4 ~30min 时钟怪癖同类，属 broker 行为，已由校准循环吸收")
    p.kv("显示换算", f"server {datetime.fromtimestamp(t.time, tz=timezone.utc).isoformat()} ≈ "
                    f"UTC {datetime.fromtimestamp(t.time - offset, tz=timezone.utc).isoformat()}")
    return offset


def probe_rates(p: Probe, mt5, offset: float | None):
    p.section("6. K 线数据（各 TF 桶偏移众数探测，contract_data §4）")
    if offset is None:
        p.fail("K 线探测", "无 tick/offset，跳过")
        return
    p.lines.append("| TF | 根数 | 首 bar(UTC) | 末 bar(UTC) | 桶偏移(step) | 一致率 |")
    p.lines.append("|----|------|-------------|-------------|--------------|--------|")
    for tf in ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]:
        tfc = getattr(mt5, f"TIMEFRAME_{tf}", None)
        if tfc is None:
            p.fail(f"TIMEFRAME_{tf}", "常量不存在")
            continue
        rates = mt5.copy_rates_from_pos(SYMBOL, tfc, 0, 3000)
        if rates is None or len(rates) == 0:
            p.fail(f"copy_rates {tf}", str(mt5.last_error()), CHECKLIST["rates"])
            continue
        times = [int(r["time"]) for r in rates]
        step = TF_SECONDS[tf]
        bucket_off, ratio = mode_of(times, step)
        first_utc = times[0] - offset
        last_utc = times[-1] - offset
        p.lines.append(
            f"| {tf} | {len(times)} | {fmt_ts(int(first_utc))} | {fmt_ts(int(last_utc))} "
            f"| {bucket_off}s | {ratio:.1%} |")
        if ratio < 0.95:
            p.warn(f"{tf} 桶一致率 {ratio:.1%} < 95%", "探测不稳定，M0 T0.9 重新探测")
    p.lines.append("")
    p.ok("形成 bar 提示", "copy_rates 末根 = forming bar（bar0）；bar1 = [-2]（INV-S1）——入库时末根不入库")


def probe_ticks_deals(p: Probe, mt5, offset: float | None):
    p.section("7. Real ticks 与 deals 流水")
    if offset is not None:
        now_utc = datetime.now(tz=timezone.utc).timestamp()
        ticks = mt5.copy_ticks_range(SYMBOL, int(now_utc - 6 * 3600), int(now_utc),
                                     mt5.COPY_TICKS_ALL)
        if ticks is None or len(ticks) == 0:
            p.warn("real ticks（近 6h）", f"空/失败: {mt5.last_error()}（CHECKLIST: rates）")
        else:
            p.ok("real ticks", f"近 6h {len(ticks)} 条（M2 real-tick 验证层可用）")
    deals = mt5.history_deals_get(int(datetime(2000, 1, 1, tzinfo=timezone.utc).timestamp()),
                                  int(datetime.now(tz=timezone.utc).timestamp()) + 86400)
    if deals is None:
        p.fail("deals 流水", str(mt5.last_error()), CHECKLIST["deals"])
    else:
        p.ok("deals 流水可读", f"{len(deals)} 条（0=空历史属正常）")


def main() -> int:
    parser = argparse.ArgumentParser(description="MT5 M0 探测")
    parser.add_argument("--path", default="", help="terminal64.exe 路径（不填则挂载已运行终端）")
    parser.add_argument("--login", type=int, default=0)
    parser.add_argument("--password", default="")
    parser.add_argument("--server", default="")
    parser.add_argument("--symbol", default=SYMBOL)
    args = parser.parse_args()

    p = Probe()
    p.section("神机 MT5 版 — M0 探测报告")
    p.kv("生成时间", datetime.now(tz=timezone.utc).isoformat() + " (UTC)")
    p.kv("目标品种", args.symbol)

    try:
        import MetaTrader5 as mt5
    except ImportError as e:
        p.section("0. 前置")
        p.fail("MetaTrader5 包", str(e), CHECKLIST["package"])
        _write_and_print(p)
        return 1

    probe_environment(p, mt5)
    init_kwargs: dict = {}
    if args.path:
        init_kwargs["path"] = args.path
    if args.login:
        init_kwargs.update(login=args.login, password=args.password, server=args.server)
    if not probe_terminal(p, mt5, init_kwargs):
        _write_and_print(p)
        return 1

    probe_account(p, mt5)
    probe_symbol(p, mt5)
    offset = probe_timezone(p, mt5)
    probe_rates(p, mt5, offset)
    probe_ticks_deals(p, mt5, offset)
    mt5.shutdown()

    if p.failures:
        p.section("结论")
        p.warn("存在未通过项", "；".join(p.failures))
        _write_and_print(p)
        return 1
    p.section("结论")
    p.ok("全部探测通过", "回填 contract_data §4/§8 并定稿（T0.9）")
    _write_and_print(p)
    return 0


def _write_and_print(p: Probe) -> None:
    out = os.path.join(REPORT_DIR, "mt5_probe_report.md")
    os.makedirs(REPORT_DIR, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(p.lines) + "\n")
    print("\n".join(p.lines))
    print(f"\n报告已写入: {out}")
    if p.failures:
        print("\n>>> 按「处理建议」逐项处理后重跑本脚本（EXECUTION_PLAN.md T0.4→T0.5）")


if __name__ == "__main__":
    raise SystemExit(main())
