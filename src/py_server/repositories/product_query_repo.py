"""产品查询/追溯的只读 SQL 汇集（不写业务、不改原始记录）。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, select

from .. import engine as eg
from .base import Conn, rows_to_dicts, with_read_conn


def list_workpieces(
    *,
    product: str | None = None,
    workpiece: str | None = None,
    device: str | None = None,
    board_status: str | None = None,
    current_step: str | None = None,
    test_step: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 200,
    conn: Conn | None = None,
) -> list[dict]:
    """按条件查询工件（产品/工件码模糊/状态/时间范围）。"""
    if conn is None:
        with with_read_conn() as c:
            return list_workpieces(
                product=product, workpiece=workpiece, device=device,
                board_status=board_status, current_step=current_step, test_step=test_step,
                date_from=date_from, date_to=date_to, limit=limit, conn=c,
            )
    w = eg.workpieces
    conds = []
    if product:
        conds.append(w.c.product == product)
    if workpiece:
        conds.append(w.c.workpiece.contains(workpiece))
    if date_from:
        conds.append(w.c.updated_at >= date_from)
    if date_to:
        conds.append(w.c.updated_at <= date_to)
    stmt = select(w)
    if conds:
        stmt = stmt.where(and_(*conds))
    stmt = stmt.order_by(w.c.updated_at.desc()).limit(limit)
    rows = rows_to_dicts(conn.execute(stmt).fetchall())

    # 补入仅在 V1.3 整单报告中的工件（未走工件主表也能查询到）
    known = {r["workpiece"] for r in rows}
    tr = eg.test_reports
    rconds = []
    if workpiece:
        rconds.append(tr.c.barcode.contains(workpiece))
    if date_from:
        rconds.append(tr.c.created_at >= date_from)
    if date_to:
        rconds.append(tr.c.created_at <= date_to)
    rstmt = select(tr).order_by(tr.c.created_at.desc()).limit(limit)
    if rconds:
        rstmt = rstmt.where(and_(*rconds))
    for report in rows_to_dicts(conn.execute(rstmt).fetchall()):
        barcode = report["barcode"]
        if barcode in known:
            continue
        if product and product != "全部":
            # 报告单没有 product 字段，无法按产品过滤，保持排除
            continue
        rows.append({
            "workpiece": barcode,
            "product": None,
            "status": "PASS" if report.get("result") == "PASS" else "FAIL",
            "current_device": report.get("station"),
            "lock_reason": None,
            "updated_at": report.get("created_at"),
        })
        known.add(barcode)
    # 合并产品流转总览（按条码）
    from . import product_flow_store, report_details_store

    flow_rows = product_flow_store.list_overview()
    flow_by_bc = {r["barcode"]: r for r in flow_rows}

    # 合并测试报告总览（统一测试报告库），用于测试工序筛选
    report_by_bc: dict[str, dict] = {}
    for rr in report_details_store.list_overview(None):
        bc = rr.get("barcode")
        if bc and bc not in report_by_bc:
            report_by_bc[bc] = rr

    for r in rows:
        bc = r["workpiece"]
        fr = flow_by_bc.get(bc)
        if fr:
            r["board_status"] = fr.get("board_status") or ""
            r["current_step"] = fr.get("current_step") or ""
            r["last_report_device"] = fr.get("last_report_device") or ""
            r["last_report_note"] = fr.get("last_report_note") or ""
            r["product"] = r.get("product") or fr.get("componentcode") or ""
        rr = report_by_bc.get(bc)
        if rr:
            r["test_step"] = rr.get("station") or ""
            r["isfinalreport"] = rr.get("isfinalreport") or ""

    # 应用新增筛选
    if device:
        rows = [r for r in rows if (r.get("current_device") or r.get("last_report_device") or "") == device]
    if board_status:
        rows = [r for r in rows if r.get("board_status") == board_status]
    if current_step:
        rows = [r for r in rows if str(r.get("current_step")) == str(current_step)]
    if test_step:
        rows = [r for r in rows if r.get("test_step") == test_step]

    rows.sort(key=lambda r: r.get("updated_at") or "", reverse=True)
    return rows[:limit]


def get_workpiece(workpiece: str, conn: Conn | None = None) -> dict | None:
    if conn is None:
        with with_read_conn() as c:
            return get_workpiece(workpiece, c)
    row = conn.execute(
        select(eg.workpieces).where(eg.workpieces.c.workpiece == workpiece)
    ).fetchone()
    if row is None:
        return None
    data = dict(row)
    data["locked"] = bool(data.get("lock_reason"))
    return data


def test_history(workpiece: str, conn: Conn | None = None) -> list[dict]:
    """按测试时间排序的测试履历。"""
    if conn is None:
        with with_read_conn() as c:
            return test_history(workpiece, c)
    tr = eg.test_results
    stmt = (
        select(tr)
        .where(tr.c.workpiece == workpiece)
        .order_by(tr.c.tested_at.asc(), tr.c.id.asc())
    )
    return rows_to_dicts(conn.execute(stmt).fetchall())


def product_route(product_model: str, conn: Conn | None = None) -> list[dict]:
    """按工艺绑定的组件号反查工艺路线。"""
    if conn is None:
        with with_read_conn() as c:
            return product_route(product_model, c)
    # 工艺绑定组件号（processes.component_no），按组件反查其工艺
    proc = conn.execute(
        select(eg.processes.c.process_code).where(eg.processes.c.component_no == product_model)
    ).fetchone()
    if proc is None or not proc[0]:
        return []
    pr = eg.process_routes
    stmt = (
        select(pr)
        .where(pr.c.process_code == proc[0])
        .order_by(pr.c.step_no)
    )
    return rows_to_dicts(conn.execute(stmt).fetchall())


def product_info(product_model: str, conn: Conn | None = None) -> dict | None:
    if conn is None:
        with with_read_conn() as c:
            return product_info(product_model, c)
    row = conn.execute(
        select(eg.products).where(eg.products.c.product_model == product_model)
    ).fetchone()
    return dict(row) if row else None


def unlock_history(workpiece: str, conn: Conn | None = None) -> list[dict]:
    if conn is None:
        with with_read_conn() as c:
            return unlock_history(workpiece, c)
    lg = eg.unlock_logs
    stmt = (
        select(lg)
        .where(lg.c.workpiece == workpiece)
        .order_by(lg.c.id.desc())
    )
    return rows_to_dicts(conn.execute(stmt).fetchall())


def distinct_products(conn: Conn | None = None) -> list[str]:
    if conn is None:
        with with_read_conn() as c:
            return distinct_products(c)
    w = eg.workpieces
    rows = conn.execute(select(w.c.product).where(w.c.product.is_not(None)).distinct().order_by(w.c.product)).fetchall()
    return [r[0] for r in rows if r[0]]


def test_reports_history(workpiece: str, conn: Conn | None = None) -> list[dict]:
    """按条码查询 V1.3 整单测试履历（主子表 JOIN，新到旧）。"""
    if conn is None:
        with with_read_conn() as c:
            return test_reports_history(workpiece, c)
    from . import report_repo

    return report_repo.list_reports(workpiece, conn)
