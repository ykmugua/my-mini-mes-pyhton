"""主数据（工序/线体/设备/程序/产品）的 SQL。唯一写 SQL 处。

返回结构与 app_pages 中 st.session_state 的 key 对齐：
steps / lines / devices / programs / program_versions / program_components /
products / product_routes / product_step_devices
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select

from .. import engine as eg
from .base import Conn, dialect_insert, rows_to_dicts, with_read_conn, with_conn


def _rows(conn: Conn, table, order_by=None) -> list[dict]:
    stmt = select(table)
    if order_by is not None:
        stmt = stmt.order_by(order_by)
    return rows_to_dicts(conn.execute(stmt).fetchall())


def _replace(conn: Conn, table, rows: list[dict], keys: list[str]) -> None:
    conn.execute(delete(table))
    if rows:
        conn.execute(table.insert(), rows)


# --- steps ---
def list_steps(conn: Conn | None = None) -> list[dict]:
    if conn is None:
        with with_read_conn() as c:
            return list_steps(c)
    rows = _rows(conn, eg.steps, eg.steps.c.step_no)
    for r in rows:
        r["enabled"] = bool(r["enabled"])
    return rows


def replace_steps(conn: Conn, rows: list[dict]) -> None:
    _replace(conn, eg.steps, rows, ["step_no"])


def delete_step(conn: Conn, step_no: int) -> None:
    conn.execute(delete(eg.steps).where(eg.steps.c.step_no == step_no))


# --- lines ---
def list_lines(conn: Conn | None = None) -> list[dict]:
    if conn is None:
        with with_read_conn() as c:
            return list_lines(c)
    return _rows(conn, eg.lines, eg.lines.c.line_id)


def replace_lines(conn: Conn, rows: list[dict]) -> None:
    _replace(conn, eg.lines, rows, ["line_id"])


# --- devices ---
def list_devices(conn: Conn | None = None) -> list[dict]:
    if conn is None:
        with with_read_conn() as c:
            return list_devices(c)
    rows = _rows(conn, eg.devices, eg.devices.c.device_id)
    for r in rows:
        r["enabled"] = bool(r["enabled"])
    return rows


def replace_devices(conn: Conn, rows: list[dict]) -> None:
    _replace(conn, eg.devices, rows, ["device_id"])


# --- programs ---
def list_programs(conn: Conn | None = None) -> list[dict]:
    if conn is None:
        with with_read_conn() as c:
            return list_programs(c)
    return _rows(conn, eg.programs, eg.programs.c.program_id)


def replace_programs(conn: Conn, rows: list[dict]) -> None:
    """整体替换程序列表（保留 program_id 便于前端关联）。"""
    conn.execute(delete(eg.programs))
    if rows:
        conn.execute(eg.programs.insert(), rows)


def list_program_versions(conn: Conn | None = None) -> list[dict]:
    if conn is None:
        with with_read_conn() as c:
            return list_program_versions(c)
    return _rows(conn, eg.program_versions, eg.program_versions.c.program_id)


def replace_program_versions(conn: Conn, rows: list[dict]) -> None:
    _replace(conn, eg.program_versions, rows, ["program_id", "program_version"])


def list_program_components(conn: Conn | None = None) -> list[dict]:
    if conn is None:
        with with_read_conn() as c:
            return list_program_components(c)
    return _rows(conn, eg.program_components, eg.program_components.c.program_id)


def replace_program_components(conn: Conn, rows: list[dict]) -> None:
    _replace(conn, eg.program_components, rows, ["program_id", "component_no"])


# --- products ---
def list_products(conn: Conn | None = None) -> list[dict]:
    if conn is None:
        with with_read_conn() as c:
            return list_products(c)
    return _rows(conn, eg.products, eg.products.c.product_model)


def replace_products(conn: Conn, rows: list[dict]) -> None:
    _replace(conn, eg.products, rows, ["product_model"])


def list_product_routes(conn: Conn | None = None) -> list[dict]:
    if conn is None:
        with with_read_conn() as c:
            return list_product_routes(c)
    return _rows(conn, eg.product_routes, eg.product_routes.c.product_model)


def replace_product_routes(conn: Conn, rows: list[dict]) -> None:
    _replace(conn, eg.product_routes, rows, ["product_model", "step_no"])


def list_product_step_devices(conn: Conn | None = None) -> list[dict]:
    if conn is None:
        with with_read_conn() as c:
            return list_product_step_devices(c)
    return _rows(conn, eg.product_step_devices, eg.product_step_devices.c.product_model)


def replace_product_step_devices(conn: Conn, rows: list[dict]) -> None:
    _replace(conn, eg.product_step_devices, rows, ["product_model", "step_no", "device_id"])


def snapshot(conn: Conn | None = None) -> dict:
    """一次性返回页面所需的全部主数据（9 个 key）。"""
    if conn is None:
        with with_read_conn() as c:
            return snapshot(c)
    return {
        "steps": list_steps(conn),
        "lines": list_lines(conn),
        "devices": list_devices(conn),
        "programs": list_programs(conn),
        "program_versions": list_program_versions(conn),
        "program_components": list_program_components(conn),
        "products": list_products(conn),
        "product_routes": list_product_routes(conn),
        "product_step_devices": list_product_step_devices(conn),
    }

def list_program_history(program_name: str, conn: Conn | None = None) -> list[dict]:
    """按程序名查询所有版本，按 program_id 从新到老排序。"""
    from sqlalchemy import select

    if conn is None:
        with with_read_conn() as c:
            return list_program_history(program_name, c)
    stmt = (
        select(eg.programs)
        .where(eg.programs.c.program_name == program_name)
        .order_by(eg.programs.c.program_id.desc())
    )
    return rows_to_dicts(conn.execute(stmt).fetchall())


def delete_program_version(conn: Conn, program_id: int) -> dict | None:
    """删除指定版本；返回被删记录（用于页面提示）。"""
    row = conn.execute(
        select(eg.programs).where(eg.programs.c.program_id == program_id)
    ).fetchone()
    if row is None:
        return None
    data = dict(row)
    conn.execute(eg.programs.delete().where(eg.programs.c.program_id == program_id))
    # 同步清理该程序的版本说明与型号关联
    conn.execute(
        eg.program_versions.delete().where(
            (eg.program_versions.c.program_id == program_id)
        )
    )
    conn.execute(
        eg.program_components.delete().where(
            eg.program_components.c.program_id == program_id
        )
    )
    return data
