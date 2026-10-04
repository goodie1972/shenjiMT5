"""tools/serve_spa.py — 静态服务 + SPA history 回退（预览/微调旧版前端 dist 用）。

用法：python tools/serve_spa.py --dir <dist目录> --port 8802
未知路径回退 index.html（vue-router createWebHistory 需要）；带扩展名的请求原样返回。
"""

from __future__ import annotations

import argparse
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class SPAHandler(SimpleHTTPRequestHandler):
    """未知无扩展名路径 → index.html（SPA 回退）；其余原样。"""

    def send_head(self):  # noqa: N802 — SimpleHTTPRequestHandler 的入口
        path = self.translate_path(self.path)
        if not os.path.exists(path) and not os.path.splitext(self.path)[1]:
            self.path = "/index.html"
        return super().send_head()

    def log_message(self, *args):  # 静默
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="SPA 静态预览服务")
    ap.add_argument("--dir", required=True, help="dist 目录")
    ap.add_argument("--port", type=int, default=8802)
    args = ap.parse_args()
    handler = partial(SPAHandler, directory=os.path.abspath(args.dir))
    print(f"SPA static → http://127.0.0.1:{args.port}/  (dir={args.dir})")
    ThreadingHTTPServer(("127.0.0.1", args.port), handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
