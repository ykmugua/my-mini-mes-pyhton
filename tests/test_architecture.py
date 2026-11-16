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
    pages = SRC / "ui" / "pages"
    if pages.exists():
        for path in pages.rglob("*.py"):
            assert "repositories" not in path.read_text(encoding="utf-8")
    for name in ("page_dashboard.py", "page_program.py", "page_interlock.py", "page_variables.py"):
        text = (SRC / "ui" / name).read_text(encoding="utf-8")
        for kw in ("sqlite3", "sqlalchemy", "repositories", "from .. import services"):
            assert kw not in text, (name, kw)
        assert "from . import client" in text, name


def test_dashboard_fragment_config_static():
    """验收 5：页面配置静态断言 run_every=10，CI 不空等 10 秒。"""
    text = (SRC / "ui" / "page_dashboard.py").read_text(encoding="utf-8")
    assert "@st.fragment(run_every=10)" in text
    # repo SQL 中含 trusted = 1
    sql = (SRC / "repositories" / "dashboard_repo.py").read_text(encoding="utf-8")
    assert "tr.c.trusted == 1" in sql


def test_dashboard_repo_sql_excludes_untrusted():
    """验收 5：合格率查询带 trusted=1；FAIL 分布查询不带 trusted 过滤。"""
    from py_server.repositories import dashboard_repo
    import inspect

    src = inspect.getsource(dashboard_repo.snapshot)
    assert "trusted_only=True" in src
    assert "_where(start, end, device, fail_only=True)" in src