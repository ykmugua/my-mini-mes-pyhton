"""架构验收：domain 无框架依赖；repositories 之外无 SQL；ui 之外无直接 DB 访问。"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "py_server"
FORBIDDEN = {"sqlalchemy", "fastapi", "streamlit", "sqlite3"}


def test_domain_has_no_framework_imports():
    for path in (SRC / "domain").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in FORBIDDEN, path
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in FORBIDDEN, path


def test_no_runtime_sql_outside_repositories():
    keywords = ("SELECT ", "INSERT ", "UPDATE ", "DELETE ", "CREATE TABLE", "ON CONFLICT")
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC).as_posix()
        if rel.startswith("repositories/") or rel == "engine.py":
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip().upper()
            assert not any(stripped.startswith(kw) for kw in keywords), (rel, lineno, line)


def test_ui_pages_only_import_client():
    """UI 层只能通过 client.py 走 HTTP，不允许直连数据层或 services。"""
    forbidden = (
        "repositories", "sqlite3", "sqlalchemy", "create_engine",
        "get_engine", "get_conn", "from .. import services",
        "from py_server import services", "from py_server.services",
    )
    ui_root = SRC / "ui"
    for path in ui_root.rglob("*.py"):
        if path.name == "client.py":
            continue
        text = path.read_text(encoding="utf-8")
        for kw in forbidden:
            assert kw not in text, (path.relative_to(SRC).as_posix(), kw)


def test_dashboard_config_static():
    """新看板静态配置：station_summary 查询、状态色、自动刷新。"""
    text = (SRC / "ui" / "page_dashboard.py").read_text(encoding="utf-8")
    assert "refresh_interval = 1000" in text
    assert "DEFAULT_COLS = 6" in text
    assert "client.station_summary" in text
    for color in ("#888888", "#4287f5", "#28a745", "#dc3545", "#333333"):
        assert color in text
    assert "@st.fragment(run_every=refresh_interval)" in text
    assert "redis" not in text.lower()


def test_dashboard_repo_sql_excludes_untrusted():
    """验收 5：合格率查询带 trusted=1；FAIL 分布查询不带 trusted 过滤。"""
    from py_server.repositories import dashboard_repo
    import inspect

    src = inspect.getsource(dashboard_repo.snapshot)
    assert "trusted_only=True" in src
    assert "_where(start, end, device, fail_only=True)" in src


def test_report_query_orchestration_lives_in_repository():
    """测试报告跨库扫描/筛选属于 repository；路由只做参数与响应。"""
    router = (SRC / "api" / "routers" / "product_query.py").read_text(encoding="utf-8")
    store = (SRC / "repositories" / "report_query_store.py").read_text(encoding="utf-8")
    assert "report_query_store." in router
    assert "SELECT " not in router.upper()
    for name in ("report_engines", "filter_options", "query_reports", "latest_traycodes"):
        assert f"def {name}" in store


def test_no_unused_ui_thin_wrappers():
    """guards/sidebar 只是无人使用的 re-export，统一由 common 提供。"""
    assert not (SRC / "ui" / "guards.py").exists()
    assert not (SRC / "ui" / "sidebar.py").exists()


def test_registry_pages_share_common_helpers():
    """四类注册页必须复用同一套公共逻辑和常量。"""
    helper = (SRC / "ui" / "pages" / "registry_helpers.py").read_text(encoding="utf-8")
    constants = (SRC / "ui" / "pages" / "constants.py").read_text(encoding="utf-8")
    for name in ("clean_text", "is_editable", "make_frame", "request_delete", "save_rows"):
        assert f"def {name}" in helper
    for name in ("ROLE_EDIT", "ROLE_VIEW", "ENABLED_OPTIONS", "EMPTY_TEXT_VALUES"):
        assert name in constants
    for page in ("device_registration.py", "tray_registration.py", "step_registration.py", "product_management.py"):
        text = (SRC / "ui" / "pages" / page).read_text(encoding="utf-8")
        assert "registry_helpers" in text, page
        assert "from .constants import" in text, page
