"""tools/qa_old_ui_baseline.py — 旧版前端原版基线截图（亮色模式，只读预览服务 8802）。

只挂静态 dist（不启动旧引擎、不连 MT4），localStorage 预置 algoforge-theme=light。
产出 tmp/old_baseline/*.png —— 原版视觉语言的基线证据。
"""

from __future__ import annotations

import os
import sys

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8802"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tmp", "old_baseline")

# 侧栏导航文案 → 文件名（点侧栏链接做客户端路由）
NAV = ["交易终端", "账户持仓", "策略中心", "历史成交", "运行配置", "日报周报", "系统日志"]


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    fails = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1600, "height": 900})
        ctx.add_init_script("localStorage.setItem('algoforge-theme','light');")
        page = ctx.new_page()
        page.goto(BASE + "/", wait_until="networkidle")
        page.wait_for_timeout(2500)          # Vue 挂载 + 首屏数据尝试（API 会失败，属预期）

        # 主题确认
        theme = page.evaluate("localStorage.getItem('algoforge-theme')")
        print(f"theme = {theme}")

        for name in NAV:
            try:
                link = page.locator(f"a:has-text('{name}'), .n-menu-item:has-text('{name}')").first
                link.click(timeout=5000)
                page.wait_for_timeout(2200)
                safe = {"交易终端": "dashboard", "账户持仓": "positions", "策略中心": "strategies",
                        "历史成交": "trades", "运行配置": "config", "日报周报": "reports",
                        "系统日志": "logs"}[name]
                out = os.path.join(OUT, f"{safe}.png")
                page.screenshot(path=out, full_page=True)
                print(f"✅ {name} → {safe}.png")
            except Exception as e:
                fails.append(name)
                print(f"❌ {name}: {str(e)[:120]}")
        browser.close()
    print(f"\n{len(NAV) - len(fails)}/{len(NAV)} 页基线截图 → {OUT}")
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
