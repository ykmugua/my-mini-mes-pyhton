"""unlock_logs 的 SQL（唯一写 SQL 处）。"""

from __future__ import annotations

from sqlalchemy import select

from .. import engine
from .base import Conn, rows_to_dicts, with_read_conn

logs = engine.unlock_logs


def insert_unlock_log(conn: Conn, row: dict) -> None:
    """插入unlock_log。"""
    conn.execute(logs.insert().values(**row))


def list_unlock_logs(conn: Conn | None = None, limit: int = 50) -> list[dict]:
    """列出unlock_logs。"""
    if conn is None:
        with with_read_conn() as c:
            return list_unlock_logs(c, limit)
    stmt = select(logs).order_by(logs.c.id.desc()).limit(limit)
    return rows_to_dicts(conn.execute(stmt).fetchall())