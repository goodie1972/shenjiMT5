"""tools/qa_dashboard.py — 监控面板 Playwright 模拟测试（真浏览器渲染验证）。

覆盖：三页面渲染断言、HTMX 挂载与自动刷新、风控表 16 行、移动端视口与
横向溢出、截图留档 tmp/qa_*.png。
用法：python tools/qa_dashboard.py   （需面板已运行于 8800）
"""

from __future__ import annotations

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from playwright.sync_api import sync_playwright  # noqa: E402

BASE = "http://127.0.0.1:8800"


def main() -> int:
    results: list[tuple[str, bool]] = []

    def check(name: str, cond) -> None:
        results.append((name, bool(cond)))
        print(f"{'✅' if cond else '❌'} {name}")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        # ── P1 总览 ──
        page.goto(BASE + "/", wait_until="networkidle")
        check("总览: 品牌标题", page.locator(".brand").first.is_visible())
        check("总览: 引擎卡片", page.locator(".card h3", has_text="引擎").first.is_visible())
        check("总览: 账户卡片", page.locator(".card h3", has_text="账户").first.is_visible())
        check("总览: 盈亏卡片", page.locator(".card h3", has_text="已实现盈亏").first.is_visible())
        check("总览: 风控表 G0~G15 共 16 行",
              page.locator("table.gates tr").count() >= 16)
        check("总览: HTMX 已加载", page.evaluate("typeof window.htmx !== 'undefined'"))
        check("总览: 自动刷新挂载",
              page.locator("[hx-get='/partials/overview']").count() == 1)
        check("总览: 心跳状态灯", page.locator(".dot").first.is_visible())
        css = page.evaluate(
            "getComputedStyle(document.body).backgroundColor")
        check(f"总览: 样式表生效（bg={css}）", css not in ("rgba(0, 0, 0, 0)", ""))
        page.wait_for_timeout(6200)                      # 跨一次 HTMX 5s 刷新
        check("总览: 5s 自动刷新后仍正常", page.locator(".dot").first.is_visible())
        page.screenshot(path="tmp/qa_overview.png", full_page=True)

        # ── P2 流水 ──
        page.goto(BASE + "/flows", wait_until="networkidle")
        check("流水: 拦截统计区块",
              page.locator(".card h3", has_text="门禁拦截统计").first.is_visible())
        check("流水: 信号表", page.locator(".card h3", has_text="信号（最近").first.is_visible())
        check("流水: 成交表", page.locator(".card h3", has_text="平仓成交").first.is_visible())
        check("流水: Journal 区块", page.locator(".card h3", has_text="Journal").first.is_visible())
        page.screenshot(path="tmp/qa_flows.png", full_page=True)

        # ── P3 影子对照 ──
        page.goto(BASE + "/shadow", wait_until="networkidle")
        check("影子: 周报区块", page.locator(".card h3", has_text="影子对照周报").first.is_visible())
        page.screenshot(path="tmp/qa_shadow.png", full_page=True)

        # ── 移动端视口（PWA 响应式）──
        mob = browser.new_page(viewport={"width": 375, "height": 812})
        mob.goto(BASE + "/", wait_until="networkidle")
        check("移动端: 总览渲染", mob.locator(".card h3", has_text="引擎").first.is_visible())
        overflow = mob.evaluate(
            "document.documentElement.scrollWidth - document.documentElement.clientWidth")
        check(f"移动端: 无横向溢出（{overflow}px）", overflow <= 2)
        check("移动端: manifest 引用", mob.locator("link[rel=manifest]").count() == 1)
        mob.screenshot(path="tmp/qa_mobile.png", full_page=True)

        # ── 404 与 token 健壮性 ──
        resp = page.request.get(BASE + "/partials/overview")
        check("健壮性: partial 直接访问 200", resp.ok)

        browser.close()

    fails = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(fails)}/{len(results)} 通过"
          + (f"；失败: {fails}" if fails else " —— 全部通过"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
