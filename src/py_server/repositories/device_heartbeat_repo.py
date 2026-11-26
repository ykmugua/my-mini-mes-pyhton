"""设备心跳仓储：记录设备最近一次在线上报时间。"""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import select

from .. import engine
from .base import Conn, dialect_insert, with_conn, with_read_conn

table = engine.device_heartbeats


def touch(device_id: str, *, conn: Conn | None = None, now_ts: int | None = None) -> int:
    """记录一次设备心跳，返回心跳时间戳。"""
    ts = int(now_ts if now_ts is not None else time.time())
    if conn is not None:
        existing = conn.execute(
            select(table.c.device_id).where(table.c.device_id == device_id)
        ).fetchone()
        if existing is None:
            conn.execute(table.insert().values(
                device_id=device_id,
                last_seen_at=ts,
                created_at=ts,
                updated_at=ts,
            ))
        else:
            conn.execute(
                table.update()
                .where(table.c.device_id == device_id)
                .values(last_seen_at=ts, updated_at=ts)
            )
        return ts
    with with_conn() as own_conn:
        return touch(device_id, conn=own_conn, now_ts=ts)


def last_seen_at(device_id: str, *, conn: Conn | None = None) -> int | None:
    """读取设备最近一次心跳时间。"""
    if conn is not None:
        row = conn.execute(
            select(table.c.last_seen_at).where(table.c.device_id == device_id)
        ).fetchone()
        return int(row[0]) if row is not None else None
    with with_read_conn() as own_conn:
        return last_seen_at(device_id, conn=own_conn)
