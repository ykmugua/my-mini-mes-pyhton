"""variables 的 SQL（唯一写 SQL 处）。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from .. import engine
from .base import Conn, rows_to_dicts, with_read_conn

v = engine.variables


def list_variables(conn: Conn | None = None, prefix: str = "") -> list[dict]:
    """列出variables。"""
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
    """获取variable_row。"""
    return conn.execute(select(v).where(v.c.name == name)).fetchone()


def exists(conn: Conn, name: str) -> bool:
    """执行 exists。"""
    return get_variable_row(conn, name) is not None


def insert_variable(conn: Conn, *, name: str, type_name: str, stored: str, now: str) -> None:
    """插入variable。"""
    conn.execute(
        v.insert().values(name=name, type=type_name, value=stored, last_device=None, updated_at=now)
    )


def update_variable(conn: Conn, *, name: str, stored: str, device_id: str, now: str) -> None:
    """更新variable。"""
    conn.execute(
        v.update()
        .where(v.c.name == name)
        .values(value=stored, last_device=device_id, updated_at=now)
    )

def delete_variable(conn: Conn, name: str) -> None:
    """删除variable。"""
    conn.execute(v.delete().where(v.c.name == name))


def rename_variable(conn: Conn, old_name: str, new_name: str) -> None:
    """执行 rename_variable。"""
    conn.execute(v.update().where(v.c.name == old_name).values(name=new_name))


def update_variable_def(conn: Conn, *, name: str, type_name: str, stored: str, now: str) -> None:
    """更新variable_def。"""
    conn.execute(
        v.update()
        .where(v.c.name == name)
        .values(type=type_name, value=stored, updated_at=now)
    )


# --- 变量读写日志 ---
lg = engine.variable_logs


def insert_log(conn: Conn, *, name: str, action: str, device_id: str, value, now: str) -> None:
    """插入log。"""
    conn.execute(
        lg.insert().values(
            name=name, action=action, device_id=device_id,
            value=None if value is None else str(value), logged_at=now,
        )
    )


def list_logs(conn: Conn | None = None, *, action: str | None = None, limit: int = 30) -> list[dict]:
    """列出logs。"""
    if conn is None:
        with with_read_conn() as c:
            return list_logs(c, action=action, limit=limit)
    stmt = select(lg)
    if action:
        stmt = stmt.where(lg.c.action == action)
    stmt = stmt.order_by(lg.c.id.desc()).limit(limit)
    return rows_to_dicts(conn.execute(stmt).fetchall())
