"""UI HTTP 客户端契约测试（不依赖真实网络）。"""

from __future__ import annotations

from py_server import config


def test_ui_api_base_uses_dedicated_env(monkeypatch):
    monkeypatch.setenv("MES_UI_API_BASE", "http://127.0.0.1:8123/")
    assert config.ui_api_base() == "http://127.0.0.1:8123"


def test_client_uses_only_http(monkeypatch):
    """client 模块不出现任何 DB / repo import。"""
    import ast
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "src" / "py_server" / "ui" / "client.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden = {"sqlalchemy", "sqlite3", "repositories"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                assert a.name.split(".")[0] not in forbidden
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in forbidden


def test_client_timeout_is_3s():
    from py_server.ui import client

    assert client.TIMEOUT_SECONDS == 3.0


def test_ui_read_fallback_on_api_error(monkeypatch):
    """失败降级：请求失败时返回上次成功数据 + 错误提示。"""
    from py_server.ui import client

    class FakeSession(dict):
        pass

    import streamlit as st
    monkeypatch.setattr(st, "session_state", FakeSession())

    def fail(*args, **kwargs):
        raise client.ApiError("boom")

    monkeypatch.setattr(client, "_request", fail)
    st.session_state["ui_cache_t"] = [{"cached": True}]

    data, error = client._cached_get("t", "/api/ui/anything")
    assert data == [{"cached": True}]
    assert error == "boom"
