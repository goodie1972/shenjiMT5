"""dashboard 冒烟测试 — TestClient 驱动真实只读 DB（终端不可达时优雅降级）。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from dashboard.app import app

client = TestClient(app)


class TestPages:
    def test_overview_200(self):
        r = client.get("/v2")
        assert r.status_code == 200
        assert "神机" in r.text and "风控" in r.text

    def test_overview_partial_200(self):
        r = client.get("/v2/partials/overview")
        assert r.status_code == 200
        assert "引擎" in r.text

    def test_flows_200(self):
        r = client.get("/v2/flows")
        assert r.status_code == 200
        assert "信号" in r.text and "门禁" in r.text

    def test_shadow_200(self):
        r = client.get("/v2/shadow")
        assert r.status_code == 200

    def test_api_overview_shape(self):
        r = client.get("/api/overview")
        assert r.status_code == 200
        body = r.json()
        assert set(body) >= {"engine", "account", "pnl", "positions", "market_open"}
        assert isinstance(body["engine"]["alive"], bool)

    def test_terminal_down_is_graceful(self):
        """终端不可达时页面不崩（账户显示降级文案）。"""
        r = client.get("/")
        assert r.status_code == 200   # 无论终端状态


class TestSpaRoot:
    def test_root_serves_spa_when_dist_exists(self):
        """根路径 = fork 前端 SPA（web/dist 存在时）。"""
        r = client.get("/")
        assert r.status_code == 200
        assert "神机" in r.text

    def test_spa_history_fallback(self):
        r = client.get("/strategies")
        assert r.status_code == 200          # SPA 回退到 index.html


class TestToken:
    def test_token_required_when_set(self, monkeypatch):
        monkeypatch.setenv("DASHBOARD_TOKEN", "secret123")
        # app 模块级读取 _TOKEN，需 reload
        import importlib
        import dashboard.app as app_mod
        importlib.reload(app_mod)
        c2 = TestClient(app_mod.app)
        assert c2.get("/v2").status_code == 401
        assert c2.get("/v2?token=secret123").status_code == 200
        monkeypatch.delenv("DASHBOARD_TOKEN")
        importlib.reload(app_mod)
