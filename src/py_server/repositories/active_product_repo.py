"""当前在制产品表（mes.db）的读写。

该表只维护当前产线上的在制产品；产品流转历史仍由 ProductFlow.db 保存。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select

from .. import db, engine as eg
from .base import Conn, rows_to_dicts, with_conn, with_read_conn


def _active():
    """返回当前在制产品表。"""
    return eg.active_products


def upsert(row: dict[str, Any], *, conn: Conn | None = None) -> None:
    """新增或更新一条当前在制产品记录。"""
    table = _active()
    values = {
        "barcode": str(row.get("barcode") or ""),
        "componentcode": str(row.get("componentcode") or ""),
        "traycode": str(row.get("traycode") or ""),
        "board_status": str(row.get("board_status") or "normal"),
        "current_step": str(row.get("current_step") or ""),
        "next_step": str(row.get("next_step") or ""),
        "last_report_device": str(row.get("last_report_device") or ""),
        "last_report_note": str(row.get("last_report_note") or ""),
        "flow_table": str(row.get("flow_table") or ""),
        "updated_at": str(row.get("updated_at") or db.utc_now_iso()),
    }
    if not values["barcode"]:
        return
    if conn is not None:
        existing = conn.execute(
            select(table.c.barcode).where(table.c.barcode == values["barcode"])
        ).fetchone()
        if existing is None:
            values["created_at"] = values["updated_at"]
            conn.execute(table.insert().values(**values))
        else:
            conn.execute(
                table.update()
                .where(table.c.barcode == values["barcode"])
                .values(**{k: v for k, v in values.items() if k != "barcode"})
            )
        return
    with with_conn() as own_conn:
        upsert(row, conn=own_conn)


def list_active(
    *,
    barcode: str | None = None,
    traycode: str | None = None,
    conn: Conn | None = None,
) -> list[dict]:
    """列出当前在制产品。"""
    table = _active()
    stmt = select(table)
    if barcode:
        stmt = stmt.where(table.c.barcode.contains(barcode))
    if traycode:
        stmt = stmt.where(table.c.traycode == traycode)
    stmt = stmt.order_by(table.c.updated_at.desc())
    if conn is not None:
        return rows_to_dicts(conn.execute(stmt).fetchall())
    with with_read_conn() as own_conn:
        return list_active(barcode=barcode, traycode=traycode, conn=own_conn)


def delete_barcodes(barcodes: list[str], *, conn: Conn | None = None) -> int:
    """删除指定条码的当前在制记录。"""
    if not barcodes:
        return 0
    table = _active()
    stmt = delete(table).where(table.c.barcode.in_([str(code) for code in barcodes]))
    if conn is not None:
        return int(getattr(conn.execute(stmt), "rowcount", 0) or 0)
    with with_conn() as own_conn:
        return delete_barcodes(barcodes, conn=own_conn)


def delete_tray(traycode: str, *, conn: Conn | None = None) -> list[dict]:
    """删除托盘下所有当前在制产品，并返回被删除的记录。"""
    table = _active()
    if conn is not None:
        rows = rows_to_dicts(conn.execute(
            select(table).where(table.c.traycode == traycode)
        ).fetchall())
        conn.execute(delete(table).where(table.c.traycode == traycode))
        return rows
    with with_conn() as own_conn:
        return delete_tray(traycode, conn=own_conn)
