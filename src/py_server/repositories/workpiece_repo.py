"""工件聚合与测试结果的 SQL（唯一写 SQL 处）。"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select, text

from .. import engine
from .base import Conn, dialect_insert, rows_to_dicts, with_read_conn

wp = engine.workpieces
tr = engine.test_results


def get_workpiece(conn: Conn, workpiece: str) -> Any | None:
    return conn.execute(select(wp).where(wp.c.workpiece == workpiece)).fetchone()


def delete_workpiece_if_no_tests(conn: Conn, workpiece: str) -> bool:
    """删除工件占位记录；仅当该条码没有测试结果/整单报告时执行。"""
    if conn.execute(select(tr.c.id).where(tr.c.workpiece == workpiece).limit(1)).fetchone():
        return False
    report_tables = conn.execute(text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'report_index_%'"
    )).fetchall()
    for (table,) in report_tables:
        if re.fullmatch(r"report_index_[A-Za-z0-9_]+", table):
            exists = conn.execute(text(
                f'SELECT 1 FROM "{table}" WHERE barcode = :bc LIMIT 1'
            ), {"bc": workpiece}).fetchone()
            if exists:
                return False
    result = conn.execute(wp.delete().where(wp.c.workpiece == workpiece))
    return bool(result.rowcount)


def public_workpiece(conn: Conn, workpiece: str) -> dict:
    row = get_workpiece(conn, workpiece)
    if row is None:
        return {"workpiece": workpiece, "exists": False}
    data = dict(row)
    data["exists"] = True
    data["locked"] = bool(data.get("lock_reason"))
    return data


def insert_workpiece_ignore(conn: Conn, *, workpiece: str, product: str | None, now: str) -> None:
    stmt = (
        dialect_insert(wp)
        .values(
            workpiece=workpiece, product=product, status="PENDING", created_at=now, updated_at=now
        )
        .on_conflict_do_nothing(index_elements=["workpiece"])
    )
    conn.execute(stmt)


def set_workpiece_product(conn: Conn, workpiece: str, product: str, now: str) -> None:
    conn.execute(
        wp.update().where(wp.c.workpiece == workpiece).values(product=product, updated_at=now)
    )


def insert_test_result_ignore(conn: Conn, row: dict) -> int:
    """写入测试结果；返回 rowcount（0 表示唯一键冲突，即重复上报）。"""
    stmt = dialect_insert(tr).values(**row)
    stmt = stmt.on_conflict_do_nothing(
        index_elements=["workpiece", "device_id", "test_item"]
    )
    result = conn.execute(stmt)
    return result.rowcount if result.rowcount is not None else 0


def get_test_result(conn: Conn, workpiece: str, device_id: str, test_item: str) -> Any | None:
    stmt = select(tr).where(
        tr.c.workpiece == workpiece,
        tr.c.device_id == device_id,
        tr.c.test_item == test_item,
    )
    return conn.execute(stmt).fetchone()


def latest_tested_at(conn: Conn, workpiece: str, exclude_id: int) -> Any | None:
    from sqlalchemy import func

    stmt = select(func.max(tr.c.tested_at)).where(
        tr.c.workpiece == workpiece, tr.c.id != exclude_id
    )
    return conn.execute(stmt).fetchone()[0]


def lock_workpiece(conn: Conn, *, workpiece: str, device_id, reason: str, now: str) -> None:
    stmt = (
        wp.update()
        .where(
            wp.c.workpiece == workpiece,
            (wp.c.lock_reason.is_(None)) | (wp.c.lock_reason == ""),
        )
        .values(lock_reason=reason, locked_at=now, lock_device=device_id, updated_at=now)
    )
    conn.execute(stmt)


def fail_workpiece(conn: Conn, *, workpiece: str, device_id: str, reason: str, now: str) -> None:
    conn.execute(
        wp.update()
        .where(wp.c.workpiece == workpiece)
        .values(
            status="FAIL",
            current_device=device_id,
            lock_reason=reason,
            locked_at=now,
            lock_device=device_id,
            updated_at=now,
        )
    )


def pass_workpiece(conn: Conn, *, workpiece: str, device_id: str, now: str) -> None:
    conn.execute(
        wp.update()
        .where(
            wp.c.workpiece == workpiece,
            (wp.c.lock_reason.is_(None)) | (wp.c.lock_reason == ""),
        )
        .values(status="PASS", current_device=device_id, updated_at=now)
    )


def list_locked(conn: Conn | None = None) -> list[dict]:
    if conn is None:
        with with_read_conn() as c:
            return list_locked(c)
    stmt = (
        select(wp)
        .where(wp.c.lock_reason.is_not(None), wp.c.lock_reason != "")
        .order_by(wp.c.locked_at.desc())
    )
    return rows_to_dicts(conn.execute(stmt).fetchall())


def unlock_workpiece_row(
    conn: Conn, *, workpiece: str, operator: str, reason: str, now: str
) -> None:
    conn.execute(
        wp.update()
        .where(wp.c.workpiece == workpiece)
        .values(
            status="PENDING",
            lock_reason=None,
            locked_at=None,
            lock_device=None,
            unlock_by=operator,
            unlock_reason=reason,
            unlocked_at=now,
            manual_release_at=now,
            updated_at=now,
        )
    )
