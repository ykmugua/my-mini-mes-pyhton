"""工位操作台用例：手动入站与托盘解绑。"""

from __future__ import annotations

from ..repositories import product_flow_store, workpiece_repo
from ..repositories.base import with_conn


def manual_inbound(
    *,
    rows: list[dict],
    now: str,
) -> None:
    """创建产品流转及工件主表记录。"""
    with with_conn() as conn:
        for row in rows:
            workpiece_repo.insert_workpiece_ignore(
                conn,
                workpiece=str(row["barcode"]),
                product=str(row["componentcode"]),
                now=now,
            )
    product_flow_store.create_inbound(rows, changed_at=now)


def unbind_tray(*, traycode: str, operator: str, now: str) -> list[dict]:
    """解除托盘绑定并删除受影响产品的当前入线状态。"""
    deleted = product_flow_store.close_tray_flow(
        traycode,
        device="托盘解绑",
        note=f"托盘解绑（操作员：{operator}）",
        changed_at=now,
    )
    with with_conn() as conn:
        for row in deleted:
            barcode = str(row.get("barcode") or "")
            if barcode:
                workpiece_repo.delete_workpiece_if_no_tests(conn, barcode)
    return deleted


def delete_product_flow(*, barcode: str) -> dict | None:
    """删除产品的入线状态，不触碰测试结果等其他业务数据。"""
    deleted = product_flow_store.delete_product(barcode)
    if deleted is None:
        return None
    with with_conn() as conn:
        workpiece_repo.delete_workpiece_if_no_tests(conn, barcode)
    return deleted


def delete_tray_flow(*, traycode: str) -> list[dict]:
    """删除整盘的当前入线状态，不触碰产品档案和测试结果。"""
    deleted = product_flow_store.delete_tray(traycode)
    if not deleted:
        return deleted
    with with_conn() as conn:
        for row in deleted:
            barcode = str(row.get("barcode") or "")
            if barcode:
                workpiece_repo.delete_workpiece_if_no_tests(conn, barcode)
    return deleted
