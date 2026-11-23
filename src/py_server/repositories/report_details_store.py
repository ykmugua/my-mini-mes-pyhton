"""测试报告详情库：一个 SQLite 文件内按工序分表。

总览表：report_index_<安全工序号>，明细表：SN_<条码>_<hash16>。
不同工序使用不同总览表，避免 details 混在一起；物理文件统一为 TestReport.db。
所有 SQL 使用 SQLAlchemy Core text() + 参数绑定；表名只允许内部派生格式。
"""

from __future__ import annotations

import hashlib
import re

from sqlalchemy import text

from .. import engine as eg


DETAIL_COLUMNS = [
    "id", "TestItem", "TestStep", "StandardValue", "UpperValue",
    "LowerValue", "MeasureValue", "TestResult", "TestBeginTime", "TestEndTime",
]

OVERVIEW_COLUMNS = [
    "id", "station", "componentcode", "traycode", "barcode",
    "programname", "programversion", "testexecutetime", "testlongtime",
    "result", "isfinalreport", "failed_step", "details_table",
]

_DETAIL_TABLE_RE = re.compile(r"SN_[0-9A-Za-z_]{1,40}_[0-9a-f]{16}")
_OVERVIEW_TABLE_RE = re.compile(r"report_index_[A-Za-z0-9_]+")


def _engine_for(engine=None):
    return engine or eg.get_details_engine()


def safe_step_no(step_no: str | int | None) -> str:
    value = re.sub(r"[^A-Za-z0-9]", "_", str(step_no or ""))
    return value or "default"


def overview_table_name(step_no: str | int | None) -> str:
    return f"report_index_{safe_step_no(step_no)}"


def detail_table_name(barcode: str, step_no: str | int | None = None) -> str:
    safe = re.sub(r"[^0-9A-Za-z_]", "_", barcode)[:40]
    identity = f"{step_no or ''}:{barcode}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    step = safe_step_no(step_no)
    return f"SN_{step}_{safe}_{digest}"


def _overview_ddl() -> str:
    return """
        id INTEGER PRIMARY KEY,
        station TEXT NOT NULL,
        componentcode TEXT NOT NULL,
        traycode TEXT NOT NULL DEFAULT '',
        barcode TEXT NOT NULL,
        programname TEXT NOT NULL,
        programversion TEXT NOT NULL,
        testexecutetime TEXT NOT NULL,
        testlongtime TEXT NOT NULL,
        result TEXT NOT NULL DEFAULT '',
        isfinalreport TEXT NOT NULL DEFAULT 'false',
        failed_step TEXT NOT NULL DEFAULT '',
        details_table TEXT NOT NULL
    """


def ensure_overview_table(step_no: str | int | None, engine=None) -> str:
    table = overview_table_name(step_no)
    if not _OVERVIEW_TABLE_RE.fullmatch(table):
        raise ValueError(f"非法总览表名: {table}")
    with _engine_for(engine).begin() as conn:
        conn.execute(text(f'CREATE TABLE IF NOT EXISTS "{table}" ({_overview_ddl()})'))
        conn.execute(text(
            f'CREATE INDEX IF NOT EXISTS "idx_{table}_barcode" ON "{table}"(barcode)'
        ))
    return table


def ensure_table(barcode: str, *, step_no: str | int | None = None, engine=None) -> str:
    table = detail_table_name(barcode, step_no)
    if not _DETAIL_TABLE_RE.fullmatch(table):
        raise ValueError(f"非法明细表名: {table}")
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


def insert_details(barcode: str, details: list[dict], *, step_no: str | int | None = None, engine=None) -> str:
    table = ensure_table(barcode, step_no=step_no, engine=engine)
    sql = text(f"""
        INSERT INTO "{table}"
        (TestItem, TestStep, StandardValue, UpperValue, LowerValue,
         MeasureValue, TestResult, TestBeginTime, TestEndTime)
        VALUES (:TestItem, :TestStep, :StandardValue, :UpperValue,
                :LowerValue, :MeasureValue, :TestResult, :TestBeginTime, :TestEndTime)
    """)
    with _engine_for(engine).begin() as conn:
        for d in details:
            conn.execute(sql, {k: d.get(k, "") for k in DETAIL_COLUMNS if k != "id"})
    return table


def insert_overview(
    report: dict,
    failed_step: str,
    *,
    step_no: str | int | None = None,
    details_table: str | None = None,
    engine=None,
) -> int:
    resolved_step = str(step_no if step_no is not None else report.get("step_no") or "")
    table = ensure_overview_table(resolved_step, engine)
    detail_table = details_table or detail_table_name(report["barcode"], resolved_step)
    if not _DETAIL_TABLE_RE.fullmatch(detail_table):
        raise ValueError(f"非法明细表名: {detail_table}")
    sql = text(f"""
        INSERT INTO "{table}"
        (station, componentcode, traycode, barcode, programname, programversion,
         testexecutetime, testlongtime, result, isfinalreport, failed_step, details_table)
        VALUES (:station, :componentcode, :traycode, :barcode, :programname,
                :programversion, :testexecutetime, :testlongtime, :result,
                :isfinalreport, :failed_step, :details_table)
    """)
    with _engine_for(engine).begin() as conn:
        conn.execute(sql, {
            "station": report.get("station", ""),
            "componentcode": report.get("componentcode", ""),
            "traycode": report.get("traycode", ""),
            "barcode": report.get("barcode", ""),
            "programname": report.get("programname", ""),
            "programversion": report.get("programversion", ""),
            "testexecutetime": report.get("testexecutetime", ""),
            "testlongtime": report.get("testlongtime", ""),
            "result": report.get("result", ""),
            "isfinalreport": str(report.get("isfinalreport", "false")),
            "failed_step": failed_step or "",
            "details_table": detail_table,
        })
        return int(conn.execute(text("SELECT last_insert_rowid()")).scalar())


def list_overview(
    barcode: str | None = None,
    *,
    step_no: str | int | None = None,
    engine=None,
) -> list[dict]:
    eng = _engine_for(engine)
    if step_no is not None:
        table = overview_table_name(step_no)
        if not _OVERVIEW_TABLE_RE.fullmatch(table):
            return []
        with eng.connect() as conn:
            exists = conn.execute(text(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name=:name"
            ), {"name": table}).scalar()
            if not exists:
                return []
            if barcode:
                result = conn.execute(
                    text(f'SELECT * FROM "{table}" WHERE barcode = :bc ORDER BY id DESC'),
                    {"bc": barcode},
                )
            else:
                result = conn.execute(text(f'SELECT * FROM "{table}" ORDER BY id DESC'))
            rows = [dict(row._mapping) for row in result.fetchall()]
            for row in rows:
                row["step_no"] = str(step_no)
            return rows

    rows: list[dict] = []
    with eng.connect() as conn:
        tables = [
            r[0]
            for r in conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name LIKE 'report_index_%' ORDER BY name"
            )).fetchall()
        ]
        for table in tables:
            if not _OVERVIEW_TABLE_RE.fullmatch(table):
                continue
            if barcode:
                result = conn.execute(
                    text(f'SELECT * FROM "{table}" WHERE barcode = :bc ORDER BY id DESC'),
                    {"bc": barcode},
                )
            else:
                result = conn.execute(text(f'SELECT * FROM "{table}" ORDER BY id DESC'))
            for row in result.fetchall():
                item = dict(row._mapping)
                item["step_no"] = table.removeprefix("report_index_")
                rows.append(item)
    return rows


def list_details(barcode: str, *, step_no: str | int | None = None, engine=None) -> list[dict]:
    return list_details_by_table(detail_table_name(barcode, step_no), engine)


def list_details_by_table(table: str, engine=None) -> list[dict]:
    if not _DETAIL_TABLE_RE.fullmatch(table or ""):
        return []
    with _engine_for(engine).connect() as conn:
        exists = conn.execute(text(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name=:name"
        ), {"name": table}).scalar()
        if not exists:
            return []
        result = conn.execute(text(f'SELECT * FROM "{table}" ORDER BY id ASC'))
        return [dict(row._mapping) for row in result.fetchall()]


def drop_all_tables() -> None:
    """测试/演示重置用：清空单库内所有工序总览表和明细表。"""
    with eg.get_details_engine().begin() as conn:
        rows = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
        for (name,) in rows:
            if name == "sqlite_sequence":
                continue
            if _OVERVIEW_TABLE_RE.fullmatch(name) or _DETAIL_TABLE_RE.fullmatch(name) or name == "report_index":
                conn.execute(text(f'DROP TABLE IF EXISTS "{name}"'))
        seq_exists = conn.execute(text(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'"
        )).scalar()
        if seq_exists:
            conn.execute(text("DROP TABLE IF EXISTS sqlite_sequence"))
