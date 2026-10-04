"""design/qa_mockups.py — 三份样稿 Playwright 截图（人工评审用）。

用法：python design/qa_mockups.py
输出：design/mockups/{A,B,C}.png（1440×900 全页）
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent.parent / "design" / "mockups"
SHOTS = ["A", "B", "C", "D"]


def main() -> int:
    fails = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        for name in SHOTS:
            path = HERE / f"{name}.html"
            if not path.exists():
                fails.append(f"{name}.html 缺失")
                continue
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(path.as_uri(), wait_until="networkidle")
            page.wait_for_timeout(1200)
            canvas = page.locator("canvas").count()
            out = HERE / f"{name}.png"
            page.screenshot(path=str(out), full_page=True)
            ok = (not errors) and canvas >= 1
            print(f"{'✅' if ok else '❌'} {name}: canvas={canvas} errors={errors[:2] or '无'} → {out.name}")
            if not ok:
                fails.append(name)
        browser.close()
    print(f"\n{len(SHOTS) - len(fails)}/{len(SHOTS)} 通过" + (f"；失败: {fails}" if fails else ""))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
