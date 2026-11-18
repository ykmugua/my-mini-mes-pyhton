"""V1.3 整单上报：主表写主库，明细写独立详情库（每产品一张表）。"""

from __future__ import annotations

from .. import engine as eg
from . import report_details_store, report_route
from .base import Conn, rows_to_dicts


def get_by_request_id(conn: Conn, request_id: str) -> dict | None:
    from sqlalchemy import select

    row = conn.execute(
        select(eg.test_reports).where(eg.test_reports.c.request_id == request_id)
    ).fetchone()
    return dict(row) if row is not None else None


def insert_report(conn: Conn, *, report: dict, details: list[dict], report_engine=None) -> int:
    """插入主表（主库事务）+ 明细（独立库）；返回主表 id。"""
    conn.execute(eg.test_reports.insert().values(**report))
    report_id = conn.lastrowid
    if report_id is None:
        from sqlalchemy import select

        row = conn.execute(
            select(eg.test_reports.c.id).where(eg.test_reports.c.request_id == report["request_id"])
        ).fetchone()
        report_id = int(row[0]) if row is not None else None
    if report_id is None:
        raise RuntimeError("failed to get inserted report id")
    # 明细写入独立库（每个产品一张表）
    report_details_store.insert_details(report["barcode"], details, report_engine)
    return report_id


def list_reports(barcode: str, conn: Conn, limit: int = 50, report_engine=None) -> list[dict]:
    """按条码查询整单（新到旧），每单带 details 列表（来自独立明细库）。"""
    from sqlalchemy import select

    tr = eg.test_reports
    rows = conn.execute(
        select(tr).where(tr.c.barcode == barcode).order_by(tr.c.id.desc()).limit(limit)
    ).fetchall()
    reports = rows_to_dicts(rows)
    for report in reports:
        # 每条报告按其 station 路由到对应工序库；未注册设备回退默认库
        eng = report_route.report_engine_for_station(report["station"], conn) if report.get("station") else report_engine
        report["details"] = report_details_store.list_details(barcode, eng)
    return reports
