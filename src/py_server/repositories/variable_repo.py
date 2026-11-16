"""variables 的 SQL（唯一写 SQL 处）。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from .. import engine
from .base import Conn, rows_to_dicts, with_read_conn

v = engine.variables


def list_variables(conn: Conn | None = None, prefix: str = "") -> list[dict]:
    if conn is None:
        with with_read_conn() as c:
            return list_variables(c, prefix)
    stmt = select(v)
    if prefix:
        escaped = prefix.replace("\\", r"\\").replace("%", r"\%").replace("_", r"\_") + "%"
        stmt = stmt.where(v.c.name.like(escaped, escape="\\"))
    stmt = stmt.order_by(v.c.name)
    return rows_to_dicts(conn.execute(stmt).fetchall())


def get_variable_row(conn: Conn, name: str) -> Any | None:
    return conn.execute(select(v).where(v.c.name == name)).fetchone()


def exists(conn: Conn, name: str) -> bool:
    return get_variable_row(conn, name) is not None


def insert_variable(conn: Conn, *, name: str, type_name: str, stored: str, now: str) -> None:
    conn.execute(
        v.insert().values(name=name, type=type_name, value=stored, last_device=None, updated_at=now)
    )


def update_variable(conn: Conn, *, name: str, stored: str, device_id: str, now: str) -> None:
    conn.execute(
        v.update()
        .where(v.c.name == name)
        .values(value=stored, last_device=device_id, updated_at=now)
    )