"""看板统计的 SQL（唯一写 SQL 处）。

合格率只统计 trusted=1；FAIL 分布保留全部（含不可信）。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, func, select

from .. import engine
from ..constants import RESULT_FAIL, RESULT_PASS
from .base import Conn, rows_to_dicts, with_read_conn

tr = engine.test_results


def _where(start: str, end: str, device: str | None, *, trusted_only: bool = False, fail_only: bool = False):
    """执行 where。"""
    conds = [tr.c.tested_at >= start, tr.c.tested_at < end]
    if device:
        conds.append(tr.c.device_id == device)
    if trusted_only:
        conds.append(tr.c.trusted == 1)
    if fail_only:
        conds.append(tr.c.result == RESULT_FAIL)
    return and_(*conds)


def _count_rows(conn: Conn, where_clause, *, with_result: bool = False) -> Any:
    """执行 count_rows。"""
    cols = [
        func.count().label("total"),
        func.coalesce(func.sum(func.IF(tr.c.result == RESULT_PASS, 1, 0)), 0).label("pass_count"),
        func.coalesce(func.sum(func.IF(tr.c.result == RESULT_FAIL, 1, 0)), 0).label("fail_count"),
    ] if with_result else [func.count().label("n")]
    return conn.execute(select(*cols).select_from(tr).where(where_clause)).fetchone()


def snapshot(conn: Conn | None, *, start: str, end: str, device: str | None) -> dict:
    """执行 snapshot。"""
    if conn is None:
        with with_read_conn() as c:
            return snapshot(c, start=start, end=end, device=device)

    totals = _count_rows(conn, _where(start, end, device), with_result=True)
    trusted = _count_rows(conn, _where(start, end, device, trusted_only=True), with_result=True)
    untrusted = conn.execute(
        select(func.count().label("n")).select_from(tr).where(
            and_(_where(start, end, device), tr.c.trusted == 0)
        )
    ).fetchone()

    by_device_stmt = (
        select(
            tr.c.device_id,
            func.count().label("total"),
            func.sum(func.IF(tr.c.result == "PASS", 1, 0)).label("pass_count"),
            func.sum(func.IF(tr.c.result == "FAIL", 1, 0)).label("fail_count"),
        )
        .select_from(tr)
        .where(_where(start, end, device, trusted_only=True))
        .group_by(tr.c.device_id)
        .order_by(tr.c.device_id)
    )
    by_device = conn.execute(by_device_stmt).fetchall()

    fail_item_stmt = (
        select(tr.c.test_item.label("label"), func.count().label("count"))
        .select_from(tr)
        .where(_where(start, end, device, fail_only=True))
        .group_by(tr.c.test_item)
        .order_by(func.count().desc(), tr.c.test_item)
    )
    fail_device_stmt = (
        select(tr.c.device_id.label("label"), func.count().label("count"))
        .select_from(tr)
        .where(_where(start, end, device, fail_only=True))
        .group_by(tr.c.device_id)
        .order_by(func.count().desc(), tr.c.device_id)
    )
    fail_by_item = conn.execute(fail_item_stmt).fetchall()
    fail_by_device = conn.execute(fail_device_stmt).fetchall()

    latest_stmt = (
        select(tr)
        .where(_where(start, end, device))
        .order_by(tr.c.id.desc())
        .limit(20)
    )
    latest = conn.execute(latest_stmt).fetchall()

    return {
        "window": (start, end),
        "totals": dict(totals),
        "trusted": dict(trusted),
        "untrusted": int(untrusted["n"]),
        "by_device": rows_to_dicts(by_device),
        "fail_by_item": rows_to_dicts(fail_by_item),
        "fail_by_device": rows_to_dicts(fail_by_device),
        "latest": rows_to_dicts(latest),
    }

def business_data_count(conn: Conn | None = None) -> int:
    """统计已有业务数据量（程序绑定 + 变量 + 工件），供 seed 判断是否需要重建。"""
    from sqlalchemy import func

    if conn is None:
        with with_read_conn() as c:
            return business_data_count(c)
    b = engine.program_bindings
    v = engine.variables
    w = engine.workpieces
    stmt = select(
        func.coalesce(func.count(), 0)
    ).select_from(b)
    # 三张表的独立计数相加
    q1 = select(func.count()).select_from(b)
    q2 = select(func.count()).select_from(v)
    q3 = select(func.count()).select_from(w)
    return int(conn.execute(q1).fetchone()[0]) + int(conn.execute(q2).fetchone()[0]) + int(conn.execute(q3).fetchone()[0])
