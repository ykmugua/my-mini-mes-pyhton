"""存储适配：SQLAlchemy Engine + 表定义（SQLAlchemy Core）。

表结构逐字对应现有 SQLite schema：
- 列名、类型（TEXT/INTEGER）、主键、AUTOINCREMENT、唯一约束、CHECK、索引全部对齐；
- 只使用 SQLAlchemy 通用类型（Text/Integer），换库只需更换 Engine；
- init_schema() 只做 metadata.create_all，不修改已有表。
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import (
    CheckConstraint,
    Column,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.engine import Engine

from . import config

metadata = MetaData()

program_bindings = Table(
    "program_bindings",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True, nullable=True),
    Column("device_id", Text, nullable=False),
    Column("product", Text, nullable=False),
    Column("program_version", Text, nullable=False),
    Column("download_url", Text, nullable=False),
    Column("sha256", Text, nullable=False),
    Column("last_pull_at", Text),
    Column("reported_version", Text),
    Column("reported_sha256", Text),
    Column("reported_at", Text),
    Column("program_ok", Integer),
    Column("updated_at", Text, nullable=False),
    UniqueConstraint("device_id", "product"),
    sqlite_autoincrement=True,
)

program_pull_logs = Table(
    "program_pull_logs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True, nullable=True),
    Column("device_id", Text, nullable=False),
    Column("product", Text, nullable=False),
    Column("program_version", Text),
    Column("sha256", Text),
    Column("pulled_at", Text, nullable=False),
    sqlite_autoincrement=True,
)
Index("idx_pull_logs_time", program_pull_logs.c.pulled_at)

program_status_logs = Table(
    "program_status_logs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True, nullable=True),
    Column("device_id", Text, nullable=False),
    Column("product", Text),
    Column("reported_version", Text),
    Column("reported_sha256", Text),
    Column("sha256_ok", Integer),
    Column("trusted", Integer, nullable=False),
    Column("reason", Text),
    Column("reported_at", Text, nullable=False),
    sqlite_autoincrement=True,
)
Index("idx_status_logs_time", program_status_logs.c.reported_at)

workpieces = Table(
    "workpieces",
    metadata,
    Column("workpiece", Text, primary_key=True, nullable=True),
    Column("product", Text),
    Column("current_device", Text),
    Column("status", Text, nullable=False, server_default="PENDING"),
    Column("lock_reason", Text),
    Column("locked_at", Text),
    Column("lock_device", Text),
    Column("unlock_by", Text),
    Column("unlock_reason", Text),
    Column("unlocked_at", Text),
    Column("manual_release_at", Text),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
)
Index("idx_workpieces_locked", workpieces.c.lock_reason, workpieces.c.locked_at)

unlock_logs = Table(
    "unlock_logs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True, nullable=True),
    Column("workpiece", Text, nullable=False),
    Column("operator", Text, nullable=False),
    Column("reason", Text, nullable=False),
    Column("device_id", Text),
    Column("lock_reason", Text),
    Column("unlocked_at", Text, nullable=False),
    sqlite_autoincrement=True,
)
Index("idx_unlock_logs_time", unlock_logs.c.unlocked_at)

test_results = Table(
    "test_results",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True, nullable=True),
    Column("workpiece", Text, nullable=False),
    Column("device_id", Text, nullable=False),
    Column("product", Text),
    Column("program_version", Text),
    Column("program_sha256", Text),
    Column("test_item", Text, nullable=False),
    Column("measured_value", Text),
    Column("result", Text, nullable=False),
    Column("tested_at", Text, nullable=False),
    Column("reported_at", Text, nullable=False),
    Column("trusted", Integer, nullable=False, server_default="1"),
    Column("untrusted_reason", Text),
    CheckConstraint("result IN ('PASS', 'FAIL')"),
    UniqueConstraint("workpiece", "device_id", "test_item"),
    sqlite_autoincrement=True,
)
Index("idx_results_reported", test_results.c.reported_at)
Index("idx_results_device", test_results.c.device_id, test_results.c.reported_at)
Index("idx_results_workpiece", test_results.c.workpiece)

variables = Table(
    "variables",
    metadata,
    Column("name", Text, primary_key=True, nullable=True),
    Column("type", Text, nullable=False),
    Column("value", Text),
    Column("last_device", Text),
    Column("updated_at", Text, nullable=False),
    CheckConstraint("type IN ('int', 'float', 'str', 'bool')"),
)

upstream_devices = Table(
    "upstream_devices",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True, nullable=True),
    Column("product", Text, nullable=False, server_default=""),
    Column("device_id", Text, nullable=False),
    Column("upstream_device_id", Text, nullable=False),
    UniqueConstraint("product", "device_id", "upstream_device_id"),
    sqlite_autoincrement=True,
)

settings = Table(
    "settings",
    metadata,
    Column("key", Text, primary_key=True, nullable=True),
    Column("value", Text),
    Column("updated_at", Text, nullable=False),
)



# 设备读写变量日志（对应程序页的拉取/上报记录）
variable_logs = Table(
    "variable_logs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True, nullable=True),
    Column("name", Text, nullable=False),
    Column("action", Text, nullable=False),  # READ / WRITE
    Column("device_id", Text, nullable=False),
    Column("value", Text),
    Column("logged_at", Text, nullable=False),
    sqlite_autoincrement=True,
)
Index("idx_variable_logs_time", variable_logs.c.logged_at)
Index("idx_variable_logs_action", variable_logs.c.action)

# -----------------------------------------------------------------------------
# 主数据（app_pages 页面接入）：工序 / 线体 / 设备 / 程序 / 产品
# -----------------------------------------------------------------------------
steps = Table(
    "steps",
    metadata,
    Column("step_no", Integer, primary_key=True, nullable=True),
    Column("step_name", Text, nullable=False),
    Column("enabled", Integer, nullable=False, default=1, server_default="1"),
    Column("remark", Text, nullable=False, default="", server_default=""),
)

lines = Table(
    "lines",
    metadata,
    Column("line_id", Text, primary_key=True, nullable=True),
    Column("line_name", Text, nullable=False),
)

devices = Table(
    "devices",
    metadata,
    Column("device_id", Text, primary_key=True, nullable=True),
    Column("device_name", Text, nullable=False),
    Column("line_id", Text, nullable=False),
    Column("step_no", Integer, nullable=False),
    Column("enabled", Integer, nullable=False, default=1, server_default="1"),
    Column("remark", Text, nullable=False, default="", server_default=""),
)

programs = Table(
    "programs",
    metadata,
    Column("program_id", Integer, primary_key=True, autoincrement=True, nullable=True),
    Column("program_name", Text, nullable=False),
    Column("program_version", Text, nullable=False),
    Column("version_description", Text, nullable=False, default="", server_default=""),
    Column("sha256", Text, nullable=False),
    Column("download_url", Text, nullable=False),
    Column("step_no", Integer, nullable=False),
    sqlite_autoincrement=True,
)

program_versions = Table(
    "program_versions",
    metadata,
    Column("program_id", Integer, nullable=False),
    Column("program_version", Text, nullable=False),
    Column("version_description", Text, nullable=False, default="", server_default=""),
    UniqueConstraint("program_id", "program_version"),
)

program_components = Table(
    "program_components",
    metadata,
    Column("program_id", Integer, nullable=False),
    Column("component_no", Text, nullable=False),
    UniqueConstraint("program_id", "component_no"),
)

products = Table(
    "products",
    metadata,
    Column("product_model", Text, primary_key=True, nullable=True),
    Column("product_name", Text, nullable=False),
    Column("test_program_name", Text, nullable=False, default="", server_default=""),
    Column("test_program_path", Text, nullable=False, default="", server_default=""),
    Column("remark", Text, nullable=False, default="", server_default=""),
)

product_routes = Table(
    "product_routes",
    metadata,
    Column("product_model", Text, nullable=False),
    Column("step_no", Integer, nullable=False),
    Column("success_next_step", Text, nullable=False),
    Column("fail_next_step", Text, nullable=False),
    UniqueConstraint("product_model", "step_no"),
)

product_step_devices = Table(
    "product_step_devices",
    metadata,
    Column("product_model", Text, nullable=False),
    Column("step_no", Integer, nullable=False),
    Column("device_id", Text, nullable=False),
    UniqueConstraint("product_model", "step_no", "device_id"),
)

_engines: dict[str, Engine] = {}


def get_engine() -> Engine:
    """按当前数据库路径获取（并缓存）Engine。"""
    path = str(config.db_path())
    engine = _engines.get(path)
    if engine is None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(f"sqlite:///{path}", future=True)

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA busy_timeout=5000")
            cur.close()

        _engines[path] = engine
    return engine


def reset_for_tests() -> None:
    """测试中切换数据库文件时清空 Engine 缓存。"""
    _engines.clear()


def init_schema() -> None:
    """只做 metadata.create_all，不修改已有表。"""
    metadata.create_all(get_engine())