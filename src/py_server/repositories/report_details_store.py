"""生产明细独立库：每个产品/条码一张明细表（物理隔离，id 从 1 开始）。

表名 = SN_<条码>_<hash16>，条码中的非法字符用下划线替换。
所有 SQL 用 SQLAlchemy Core text() + 参数绑定；只允许内部派生的表名。
"""

from __future__ import annotations

import hashlib

from sqlalchemy import text

from .. import engine as eg
from .base import Conn as MainConn

def _engine_for(engine=None):
    return engine or eg.get_details_engine()


DETAIL_COLUMNS = [
    "id", "TestItem", "TestStep", "StandardValue", "UpperValue",
    "LowerValue", "MeasureValue", "TestResult", "TestBeginTime", "TestEndTime",
]


def detail_table_name(barcode: str) -> str:
    import re

    safe = re.sub(r"[^0-9A-Za-z_]", "_", barcode)[:40]
    digest = hashlib.sha256(barcode.encode("utf-8")).hexdigest()[:16]
    return f"SN_{safe}_{digest}"


def ensure_table(barcode: str, engine=None) -> str:
    table = detail_table_name(barcode)
    with _engine_for(engine).begin() as conn:
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS "{table}" (
                id INTEGER PRIMARY KEY,
                TestItem TEXT NOT NULL,
                TestStep TEXT NOT NULL,
                StandardValue TEXT NOT NULL,
                UpperValue TEXT NOT NULL,
                LowerValue TEXT NOT NULL,
                MeasureValue TEXT NOT NULL,
                TestResult TEXT NOT NULL,
                TestBeginTime TEXT NOT NULL,
                TestEndTime TEXT NOT NULL
            )
        """))
    return table


def insert_details(barcode: str, details: list[dict], engine=None) -> None:
    table = ensure_table(barcode, engine)
    sql = text(f"""
        INSERT INTO "{table}"
        (TestItem, TestStep, StandardValue, UpperValue, LowerValue,
         MeasureValue, TestResult, TestBeginTime, TestEndTime)
        VALUES (:TestItem, :TestStep, :StandardValue, :UpperValue,
                :LowerValue, :MeasureValue, :TestResult, :TestBeginTime, :TestEndTime)
    """)
    with _engine_for(engine).begin() as conn:
        for d in details:
            conn.execute(sql, {
                k: d.get(k, "") for k in DETAIL_COLUMNS if k != "id"
            })


def list_details(barcode: str, engine=None) -> list[dict]:
    table = detail_table_name(barcode)
    with _engine_for(engine).connect() as conn:
        result = conn.execute(text(f'SELECT * FROM "{table}" ORDER BY id ASC'))
        return [dict(row._mapping) for row in result.fetchall()]


def drop_product_table(barcode: str) -> None:
    table = detail_table_name(barcode)
    with _engine_for(engine).begin() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS "{table}"'))


def drop_all_tables() -> None:
    """测试/演示重置用：清空独立明细库中的所有产品表。"""
    with eg.get_details_engine().begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS report_index"))
        rows = conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )).fetchall()
        for row in rows:
            name = row[0]
            if name == "sqlite_sequence" or name == "report_index":
                continue
            if name.startswith("SN_"):
                conn.execute(text(f'DROP TABLE IF EXISTS "{name}"'))
        # 删除自增序列残留，保证重建后 id 从 1 开始（表不存在时忽略）
        seq_exists = conn.execute(text(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'"
        )).scalar()
        if seq_exists:
            conn.execute(text("DROP TABLE IF EXISTS sqlite_sequence"))


# 总览表（details.db 内）：每次整单上报一行，指向该产品的明细表
OVERVIEW_COLUMNS = [
    "id", "linecode", "station", "componentcode", "barcode",
    "programname", "programversion", "testexecutetime", "testlongtime",
    "details_table", "isfinalreport", "failed_step",
]


def ensure_overview_table(engine=None) -> None:
    with _engine_for(engine).begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS report_index (
                id INTEGER PRIMARY KEY,
                linecode TEXT NOT NULL,
                station TEXT NOT NULL,
                componentcode TEXT NOT NULL,
                barcode TEXT NOT NULL,
                programname TEXT NOT NULL,
                programversion TEXT NOT NULL,
                testexecutetime TEXT NOT NULL,
                testlongtime TEXT NOT NULL,
                details_table TEXT NOT NULL,
                isfinalreport TEXT NOT NULL DEFAULT 'false',
                failed_step TEXT NOT NULL DEFAULT ''
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_report_index_barcode ON report_index(barcode)"
        ))


def insert_overview(report: dict, failed_step: str, engine=None) -> int:
    """写入总览表；details_table 指向该条码的明细表名。"""
    ensure_overview_table(engine)
    table = detail_table_name(report["barcode"])
    sql = text("""
        INSERT INTO report_index
        (linecode, station, componentcode, barcode, programname, programversion,
         testexecutetime, testlongtime, details_table, isfinalreport, failed_step)
        VALUES (:linecode, :station, :componentcode, :barcode, :programname,
                :programversion, :testexecutetime, :testlongtime,
                :details_table, :isfinalreport, :failed_step)
    """)
    with _engine_for(engine).begin() as conn:
        conn.execute(sql, {
            "linecode": report.get("linecode", ""),
            "station": report.get("station", ""),
            "componentcode": report.get("componentcode", ""),
            "barcode": report.get("barcode", ""),
            "programname": report.get("programname", ""),
            "programversion": report.get("programversion", ""),
            "testexecutetime": report.get("testexecutetime", ""),
            "testlongtime": report.get("testlongtime", ""),
            "details_table": table,
            "isfinalreport": str(report.get("isfinalreport", "false")),
            "failed_step": failed_step or "",
        })
        result = conn.execute(text("SELECT last_insert_rowid()"))
        return int(result.scalar())


def list_overview(barcode: str | None = None, engine=None) -> list[dict]:
    ensure_overview_table(engine)
    with _engine_for(engine).connect() as conn:
        if barcode:
            result = conn.execute(
                text("SELECT * FROM report_index WHERE barcode = :bc ORDER BY id DESC"),
                {"bc": barcode},
            )
        else:
            result = conn.execute(text("SELECT * FROM report_index ORDER BY id DESC"))
        return [dict(row._mapping) for row in result.fetchall()]


def list_details_by_table(table: str, engine=None) -> list[dict]:
    """按表名读取明细（表名必须已校验为 16 位 hex）。"""
    with _engine_for(engine).connect() as conn:
        result = conn.execute(text(f'SELECT * FROM "{table}" ORDER BY id ASC'))
        return [dict(row._mapping) for row in result.fetchall()]
