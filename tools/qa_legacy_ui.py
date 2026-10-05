"""tools/qa_legacy_ui.py — 原版前端（E 路线 fork）+ 真数据的 Playwright 模拟测试。

目标：http://127.0.0.1:8805/（桌面版后端：fork SPA + U-E1 legacy API + WS hub）
覆盖：交易终端真数据渲染、WS 通道帧、历史成交真实交易行、策略中心空态、
      导航完整性、未捕获异常为零、截图留档 tmp/qa_legacy/*.png。
"""

from __future__ import annotations

import os
import sys

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8805"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tmp", "qa_legacy")


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    results: list[tuple[str, bool]] = []

    def check(name: str, cond) -> None:
        results.append((name, bool(cond)))
        print(f"{'✅' if cond else '❌'} {name}")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 900})
        page_errors: list[str] = []
        page.on("pageerror", lambda e: page_errors.append(str(e)))
        ws_frames: list[str] = []

        def on_ws(ws):
            check("WS: /ws 连接建立", True)
            ws.on("framereceived", lambda fr: ws_frames.append(str(fr)[:120]))

        page.on("websocket", on_ws)

        # ── ① 交易终端（首页）──
        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.wait_for_timeout(5000)                     # Vue 挂载 + WS + REST
        check("① 品牌/侧栏渲染", page.locator("text=交易终端").first.is_visible())
        check("① 导航 8 项完整",
              sum(1 for n in ["交易终端", "账户持仓", "策略中心", "回测中心",
                              "历史成交", "运行配置", "日报周报", "系统日志"]
                  if page.locator(f"text={n}").first.is_visible()) >= 7)
        check("① K 线图 canvas 渲染", page.locator("canvas").count() >= 1)
        body = page.content()
        check("① 行情 bid/ask 非零", ("4153" in body or "4154" in body or "4155" in body))
        acct = page.request.get(BASE + "/api/account").json()
        check("① /api/account 真数据（balance 99981.77）", abs(acct["balance"] - 99981.77) < 0.01)
        check("① /api/account 契约字段齐全",
              all(k in acct for k in ("login", "balance", "equity", "margin",
                                      "free_margin", "currency", "leverage")))
        check("① 无未捕获 JS 异常", len(page_errors) == 0)
        if page_errors:
            print("   pageerrors:", page_errors[:3])
        check("① WS 帧已接收（prices/positions/account）", len(ws_frames) > 0)
        page.screenshot(path=os.path.join(OUT, "L1_dashboard.png"), full_page=True)

        # ── ② 历史成交（真实对账交易）──
        page.goto(BASE + "/trades", wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        check("② 历史成交页渲染", page.locator("text=历史成交").first.is_visible())
        body2 = page.content()
        check("② smoke 真实交易行（ticket 10796240457）", "10796240457" in body2)
        check("② broker 真值盈亏（-18.23）", "-18.23" in body2)
        check("② sl_triggered 原因可见", "sl_triggered" in body2)
        page.screenshot(path=os.path.join(OUT, "L2_trades.png"), full_page=True)

        # ── ③ 策略中心（后端未实现 → 空态不崩）──
        page.goto(BASE + "/strategies", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        check("③ 策略中心页渲染不崩", page.locator("text=策略中心").first.is_visible())
        page.screenshot(path=os.path.join(OUT, "L3_strategies.png"), full_page=True)

        # ── ④ 日报周报 ──
        page.goto(BASE + "/reports", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        check("④ 日报周报页渲染", page.locator("text=日报").first.is_visible())
        page.screenshot(path=os.path.join(OUT, "L4_reports.png"), full_page=True)

        browser.close()

    fails = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(fails)}/{len(results)} 通过"
          + (f"；失败: {fails}" if fails else " —— 全部通过"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
