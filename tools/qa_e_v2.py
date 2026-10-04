"""tools/qa_e_v2.py — E 微调层 v2 截图（用户裁定后：影子对照并入日报周报页）。

前置：tools/serve_spa.py --dir design/mockups/E_original_dist --port 8803 已在跑。
产出：tmp/e_tuned_v2/*.png
"""

from __future__ import annotations

import os

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8803"
OUT = os.path.join("tmp", "e_tuned_v2")


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1600, "height": 900})
        ctx.add_init_script("localStorage.setItem('algoforge-theme','light');")
        page = ctx.new_page()
        page.goto(BASE + "/", wait_until="networkidle")
        page.wait_for_timeout(3000)

        # ① 原样首页（v2 override：无任何注入痕迹——两个导航项已撤销）
        page.screenshot(path=os.path.join(OUT, "E2v2_首页_原样.png"), full_page=True)
        print("① 首页原样 ✓（v1 的两个新增导航项已撤销）")

        # ② 点侧栏「日报周报」→ 影子对照卡片注入演示
        link = page.locator("a:has-text('日报周报'), .n-menu-item:has-text('日报周报')").first
        link.click(timeout=5000)
        page.wait_for_timeout(2500)                      # 路由 + override 轮询
        injected = page.locator("#e-shadow-card").count()
        page.screenshot(path=os.path.join(OUT, "E2v2_日报周报_影子对照卡片.png"), full_page=True)
        print(f"② 日报周报页 ✓ ｜ 影子对照卡片注入: {'✅' if injected else '❌ 未出现'}")

        b.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
