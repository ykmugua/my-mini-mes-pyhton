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
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 200,
    conn: Conn | None = None,
) -> list[dict]:
    """按条件查询工件（产品/工件码模糊/状态/时间范围）。"""
    if conn is None:
        with with_read_conn() as c:
            return list_workpieces(
                product=product, workpiece=workpiece, status=status,
                date_from=date_from, date_to=date_to, limit=limit, conn=c,
            )
    w = eg.workpieces
    conds = []
    if product:
        conds.append(w.c.product == product)
    if workpiece:
        conds.append(w.c.workpiece.contains(workpiece))
    if status:
        conds.append(w.c.status == status)
    if date_from:
        conds.append(w.c.updated_at >= date_from)
    if date_to:
        conds.append(w.c.updated_at <= date_to)
    stmt = select(w)
    if conds:
        stmt = stmt.where(and_(*conds))
    stmt = stmt.order_by(w.c.updated_at.desc()).limit(limit)
    return rows_to_dicts(conn.execute(stmt).fetchall())


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
    if conn is None:
        with with_read_conn() as c:
            return product_route(product_model, c)
    pr = eg.product_routes
    stmt = (
        select(pr)
        .where(pr.c.product_model == product_model)
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