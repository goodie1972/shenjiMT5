"""tools/qa_e_tuned.py — E 微调版截图（原版 dist 100% 保留 + override 只加两项）。

前置：tools/serve_spa.py --dir design/mockups/E_original_dist --port 8803 已在跑。
产出：tmp/e_tuned/*.png
"""

from __future__ import annotations

import os

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8803"
OUT = os.path.join("tmp", "e_tuned")


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1600, "height": 900})
        ctx.add_init_script("localStorage.setItem('algoforge-theme','light');")
        page = ctx.new_page()
        page.goto(BASE + "/", wait_until="networkidle")
        page.wait_for_timeout(3500)                      # Vue 挂载 + override 注入

        # ① 原样首页 + 侧栏两项新增（字体/底色/布局零变更）
        page.screenshot(path=os.path.join(OUT, "E1_原样+新增导航.png"), full_page=True)
        print("E1 ✓ 原样首页 + 新增导航")

        # ② AI 参谋占位面板
        page.locator("#e-nav-ai").click(timeout=5000)
        page.wait_for_timeout(600)
        page.screenshot(path=os.path.join(OUT, "E2_AI参谋占位.png"))
        print("E2 ✓ AI 参谋占位面板")

        # ③ 影子对照占位面板
        page.locator("#e-nav-shadow").click(timeout=5000)
        page.wait_for_timeout(600)
        page.screenshot(path=os.path.join(OUT, "E3_影子对照占位.png"))
        print("E3 ✓ 影子对照占位面板")

        b.close()
    print(f"完成 → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
