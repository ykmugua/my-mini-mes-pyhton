"""station_summary 只读查询（前端看板专用，不写入、不计算业务逻辑）。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from .. import engine
from .base import Conn, rows_to_dicts, with_read_conn

ss = engine.station_summary


def get_by_device(device_id: str, conn: Conn | None = None) -> dict | None:
    """按设备编号读取汇总记录；查不到返回 None。"""
    if conn is None:
        with with_read_conn() as c:
            return get_by_device(device_id, c)
    row = conn.execute(select(ss).where(ss.c.device_id == device_id)).fetchone()
    return dict(row) if row is not None else None


def get_all(conn: Conn | None = None) -> list[dict]:
    if conn is None:
        with with_read_conn() as c:
            return get_all(c)
    return rows_to_dicts(conn.execute(select(ss)).fetchall())

def list_fail_details(device_id: str, conn: Conn | None = None, limit: int = 50) -> list[dict]:
    """按设备读取失败项明细（只读）。"""
    from sqlalchemy import select

    if conn is None:
        with with_read_conn() as c:
            return list_fail_details(device_id, c, limit)
    fd = engine.station_fail_detail
    stmt = (
        select(fd)
        .where(fd.c.device_id == device_id)
        .order_by(fd.c.id.desc())
        .limit(limit)
    )
    return rows_to_dicts(conn.execute(stmt).fetchall())
