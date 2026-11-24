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
# 主数据（app_pages 页面接入）：工序 / 设备 / 程序 / 产品
# -----------------------------------------------------------------------------
steps = Table(
    "steps",
    metadata,
    Column("step_no", Text, primary_key=True, nullable=True),
    Column("step_name", Text, nullable=False),
    Column("enabled", Integer, nullable=False, default=1, server_default="1"),
    Column("remark", Text, nullable=False, default="", server_default=""),
)

devices = Table(
    "devices",
    metadata,
    Column("device_id", Text, primary_key=True, nullable=True),
    Column("device_name", Text, nullable=False),
    Column("device_model", Text, nullable=False, default="", server_default=""),
    Column("step_no", Text, nullable=False, default="", server_default=""),
    Column("enabled", Integer, nullable=False, default=1, server_default="1"),
    Column("remark", Text, nullable=False, default="", server_default=""),
)

trays = Table(
    "trays",
    metadata,
    Column("traycode", Text, primary_key=True, nullable=True),
    Column("tray_name", Text, nullable=False),
    Column("tray_model", Text, nullable=False, default="", server_default=""),
    Column("capacity", Integer, nullable=False, default=1, server_default="1"),
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
    Column("step_no", Text, nullable=False, default="", server_default=""),
    Column("enabled", Integer, nullable=False, default=1, server_default="1"),
    sqlite_autoincrement=True,
)

program_versions = Table(
    "program_versions",
    metadata,
    Column("program_id", Integer, nullable=False),
    Column("program_version", Text, nullable=False),
    Column("version_description", Text, nullable=False, default="", server_default=""),
    Column("sha256", Text, nullable=False, default="", server_default=""),
    Column("download_url", Text, nullable=False, default="", server_default=""),
    UniqueConstraint("program_id", "program_version"),
)

products = Table(
    "products",
    metadata,
    Column("product_model", Text, primary_key=True, nullable=True),
    Column("product_name", Text, nullable=False),
    Column("test_program_name", Text, nullable=False, default="", server_default=""),
    Column("test_program_path", Text, nullable=False, default="", server_default=""),
    Column("remark", Text, nullable=False, default="", server_default=""),
    Column("enabled", Integer, nullable=False, default=1, server_default="1"),
)

processes = Table(
    "processes",
    metadata,
    Column("process_code", Text, primary_key=True, nullable=True),
    Column("process_name", Text, nullable=False),
    Column("enabled", Integer, nullable=False, default=1, server_default="1"),
    Column("remark", Text, nullable=False, default="", server_default=""),
    Column("source_process_code", Text, nullable=False, default="", server_default=""),
    Column("component_no", Text, nullable=False, default="", server_default=""),
)

process_routes = Table(
    "process_routes",
    metadata,
    Column("process_code", Text, nullable=False),
    Column("step_no", Text, nullable=False),
    Column("success_next_step", Text, nullable=False),
    Column("fail_next_step", Text, nullable=False),
    UniqueConstraint("process_code", "step_no"),
)

process_step_resources = Table(
    "process_step_resources",
    metadata,
    Column("process_code", Text, nullable=False),
    Column("step_no", Text, nullable=False),
    Column("program_name", Text, nullable=False, default="", server_default=""),
    Column("device_models", Text, nullable=False, default="", server_default=""),
    Column("tray_models", Text, nullable=False, default="", server_default=""),
    UniqueConstraint("process_code", "step_no"),
)


# V1.3 整单测试结果上报：主表（一次上报一单）
test_reports = Table(
    "test_reports",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True, nullable=True),
    Column("request_id", Text, nullable=False, unique=True),
    Column("station", Text, nullable=False),
    Column("componentcode", Text, nullable=False),
    Column("barcode", Text, nullable=False),
    Column("programname", Text, nullable=False),
    Column("programversion", Text, nullable=False),
    Column("testexecutetime", Text, nullable=False),
    Column("result", Text, nullable=False),
    Column("testlongtime", Text, nullable=False),
    Column("isfinalreport", Text, nullable=False, default="false", server_default="false"),
    Column("created_at", Text, nullable=False),
    sqlite_autoincrement=True,
)

# 产线工站监控汇总表（业务后端维护，前端只读）
station_summary = Table(
    "station_summary",
    metadata,
    Column("device_id", Text, primary_key=True, nullable=True),
    Column("name", Text, nullable=False, default="", server_default=""),
    Column("status", Text, nullable=False, default="禁用", server_default="禁用"),
    Column("barcode", Text, nullable=False, default="无条码", server_default="无条码"),
    Column("total", Integer, nullable=False, default=0, server_default="0"),
    Column("first_pass", Integer, nullable=False, default=0, server_default="0"),
    Column("retest_pass", Integer, nullable=False, default=0, server_default="0"),
    Column("fail", Integer, nullable=False, default=0, server_default="0"),
    Column("status_since", Integer),          # 当前状态开始时间（unix 秒）
    Column("test_duration", Integer),          # 最近一次测试用时（秒），通过/失败时显示
)


# 失败项明细（后端维护，前端只读；供看板「详细」页签展示）
station_fail_detail = Table(
    "station_fail_detail",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True, nullable=True),
    Column("device_id", Text, nullable=False),
    Column("test_item", Text, nullable=False),
    Column("barcode", Text, nullable=False),
    Column("failed_at", Text),
    sqlite_autoincrement=True,
)

_engines: dict[str, Engine] = {}
_details_engines: dict[str, Engine] = {}
_report_engines: dict[str, Engine] = {}
_flow_engines: dict[str, Engine] = {}


def get_details_engine() -> Engine:
    """生产明细独立库（与主库物理分离，按产品分表）。"""
    path = str(config.details_db_path())
    engine = _details_engines.get(path)
    if engine is None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(f"sqlite:///{path}", future=True)

        @event.listens_for(engine, "connect")
        def _details_sqlite_pragmas(dbapi_conn, _):
            """执行 details_sqlite_pragmas。"""
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.execute("PRAGMA busy_timeout=5000")
            cur.close()

        _details_engines[path] = engine
    return engine




def _open_engine(path: Path | str, *, foreign_keys: bool = False) -> Engine:
    """创建 SQLite Engine（统一 WAL/busy_timeout 配置）。"""
    path = str(path)
    eng = create_engine(f"sqlite:///{path}", future=True)

    @event.listens_for(eng, "connect")
    def _pragmas(dbapi_conn, _):
        """执行 pragmas。"""
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        if foreign_keys:
            cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    return eng


def get_report_engine(step_no: str | int) -> Engine:
    """获取测试报告库 Engine；所有工序现在共用同一个数据库文件。"""
    return get_details_engine()


def get_product_flow_engine() -> Engine:
    """产品流转库 Engine（ProductFlow.db）。"""
    path = str(config.product_flow_db_path())
    eng = _flow_engines.get(path)
    if eng is None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        eng = _open_engine(path)
        _flow_engines[path] = eng
    return eng


def get_engine() -> Engine:
    """按当前数据库路径获取（并缓存）Engine。"""
    path = str(config.db_path())
    engine = _engines.get(path)
    if engine is None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(f"sqlite:///{path}", future=True)

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _):
            """执行 sqlite_pragmas。"""
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
    _details_engines.clear()
    _report_engines.clear()
    _flow_engines.clear()


def init_schema() -> None:
    """只做 metadata.create_all，不修改已有表。"""
    metadata.create_all(get_engine())
