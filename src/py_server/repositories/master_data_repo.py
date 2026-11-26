"""主数据（工序/线体/设备/程序/产品）的 SQL。唯一写 SQL 处。

返回结构与 app_pages 中 st.session_state 的 key 对齐：
steps / devices / programs / products / processes
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select

from .. import engine as eg
from .base import Conn, dialect_insert, rows_to_dicts, with_read_conn, with_conn


def _rows(conn: Conn, table, order_by=None) -> list[dict]:
    """执行 rows。"""
    stmt = select(table)
    if order_by is not None:
        stmt = stmt.order_by(order_by)
    return rows_to_dicts(conn.execute(stmt).fetchall())


def _replace(conn: Conn, table, rows: list[dict], keys: list[str]) -> None:
    """执行 replace。"""
    conn.execute(delete(table))
    if rows:
        conn.execute(table.insert(), rows)


# --- steps ---
def list_steps(conn: Conn | None = None) -> list[dict]:
    """列出steps。"""
    if conn is None:
        with with_read_conn() as c:
            return list_steps(c)
    rows = _rows(conn, eg.steps, eg.steps.c.step_no)
    for r in rows:
        r["enabled"] = bool(r["enabled"])
    return rows


def replace_steps(conn: Conn, rows: list[dict]) -> None:
    """替换steps。"""
    _replace(conn, eg.steps, rows, ["step_no"])


def delete_step(conn: Conn, step_no: str | int) -> None:
    """删除step。"""
    conn.execute(delete(eg.steps).where(eg.steps.c.step_no == step_no))


# --- devices ---
def list_devices(conn: Conn | None = None) -> list[dict]:
    """列出devices。"""
    if conn is None:
        with with_read_conn() as c:
            return list_devices(c)
    rows = _rows(conn, eg.devices, eg.devices.c.device_id)
    for r in rows:
        r["enabled"] = bool(r["enabled"])
    return rows


def replace_devices(conn: Conn, rows: list[dict]) -> None:
    """替换devices。"""
    _replace(conn, eg.devices, rows, ["device_id"])


# --- trays ---
def list_trays(conn: Conn | None = None) -> list[dict]:
    """列出trays。"""
    if conn is None:
        with with_read_conn() as c:
            return list_trays(c)
    rows = _rows(conn, eg.trays, eg.trays.c.traycode)
    for r in rows:
        r["enabled"] = bool(r["enabled"])
    return rows


def replace_trays(conn: Conn, rows: list[dict]) -> None:
    """替换trays。"""
    _replace(conn, eg.trays, rows, ["traycode"])


# --- needle_beds ---
def list_needle_beds(conn: Conn | None = None) -> list[dict]:
    """列出needle_beds。"""
    if conn is None:
        with with_read_conn() as c:
            return list_needle_beds(c)
    rows = _rows(conn, eg.needle_beds, eg.needle_beds.c.needle_bed_code)
    for row in rows:
        row["enabled"] = bool(row["enabled"])
    return rows


def replace_needle_beds(conn: Conn, rows: list[dict]) -> None:
    """替换needle_beds。"""
    _replace(conn, eg.needle_beds, rows, ["needle_bed_code"])


# --- programs ---
def list_programs(conn: Conn | None = None) -> list[dict]:
    """列出programs。"""
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
    """列出program_versions。"""
    if conn is None:
        with with_read_conn() as c:
            return list_program_versions(c)
    return _rows(conn, eg.program_versions, eg.program_versions.c.program_id)


def replace_program_versions(conn: Conn, rows: list[dict]) -> None:
    """替换program_versions。"""
    _replace(conn, eg.program_versions, rows, ["program_id", "program_version"])


# --- processes ---
def list_processes(conn: Conn | None = None) -> list[dict]:
    """列出processes。"""
    if conn is None:
        with with_read_conn() as c:
            return list_processes(c)
    rows = _rows(conn, eg.processes, eg.processes.c.process_code)
    for r in rows:
        r["enabled"] = bool(r["enabled"])
    return rows


def replace_processes(conn: Conn, rows: list[dict]) -> None:
    """替换processes。"""
    _replace(conn, eg.processes, rows, ["process_code"])


# --- process_routes ---
def list_process_routes(conn: Conn | None = None) -> list[dict]:
    """列出process_routes。"""
    if conn is None:
        with with_read_conn() as c:
            return list_process_routes(c)
    return _rows(conn, eg.process_routes, eg.process_routes.c.process_code)


def replace_process_routes(conn: Conn, rows: list[dict]) -> None:
    """替换process_routes。"""
    _replace(conn, eg.process_routes, rows, ["process_code", "step_no"])


# --- process_step_resources ---
def list_process_step_resources(conn: Conn | None = None) -> list[dict]:
    """列出process_step_resources。"""
    if conn is None:
        with with_read_conn() as c:
            return list_process_step_resources(c)
    return _rows(conn, eg.process_step_resources, eg.process_step_resources.c.process_code)


def replace_process_step_resources(conn: Conn, rows: list[dict]) -> None:
    """替换process_step_resources。"""
    _replace(conn, eg.process_step_resources, rows, ["process_code", "step_no"])


# --- products ---
def list_products(conn: Conn | None = None) -> list[dict]:
    """列出products。"""
    if conn is None:
        with with_read_conn() as c:
            return list_products(c)
    return _rows(conn, eg.products, eg.products.c.product_model)


def replace_products(conn: Conn, rows: list[dict]) -> None:
    """替换products。"""
    _replace(conn, eg.products, rows, ["product_model"])


def snapshot(conn: Conn | None = None) -> dict:
    """一次性返回页面所需的全部主数据（9 个 key）。"""
    if conn is None:
        with with_read_conn() as c:
            return snapshot(c)
    return {
        "steps": list_steps(conn),
        "devices": list_devices(conn),
        "trays": list_trays(conn),
        "needle_beds": list_needle_beds(conn),
        "programs": list_programs(conn),
        "program_versions": list_program_versions(conn),
        "products": list_products(conn),
        "processes": list_processes(conn),
        "process_routes": list_process_routes(conn),
        "process_step_resources": list_process_step_resources(conn),
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
    # 同步清理该程序的版本说明
    conn.execute(
        eg.program_versions.delete().where(
            (eg.program_versions.c.program_id == program_id)
        )
    )
    return data
