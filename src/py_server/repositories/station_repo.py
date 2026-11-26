"""station_summary 只读查询（前端看板专用，不写入、不计算业务逻辑）。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from .. import db, engine
from ..constants import DEVICE_STATUS_TESTING, STATUS_FAIL_TEXT, STATUS_PASS_TEXT
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
    """获取all。"""
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


# ---------------------------------------------------------------------------
# 写入：由测试结果上报用例调用（唯一写 station_summary 的地方）
# ---------------------------------------------------------------------------


def ensure_device(conn: Conn, device_id: str, name: str) -> None:
    """汇总表中没有该设备时初始化一行（状态默认禁用，等进站/结果再更新）。"""
    if get_by_device(device_id, conn) is None:
        conn.execute(
            ss.insert().values(
                device_id=device_id,
                name=name or device_id,
                status="禁用",
                barcode="无条码",
                total=0,
                first_pass=0,
                retest_pass=0,
                fail=0,
            )
        )


def apply_result(
    conn: Conn,
    *,
    device_id: str,
    name: str,
    barcode: str,
    result: str,
    is_retest: bool,
    duration_seconds: int,
    status_since: int,
    failed_items: list[str],
) -> None:
    """按一次测试结果更新汇总 + 失败明细（单一事务内调用）。"""
    from sqlalchemy import func, select

    ensure_device(conn, device_id, name)
    status = STATUS_PASS_TEXT if result == "PASS" else STATUS_FAIL_TEXT
    if is_retest:
        retest_inc = 1 if result == "PASS" else 0
        first_inc = 0
    else:
        first_inc = 1 if result == "PASS" else 0
        retest_inc = 0
    fail_inc = 1 if result == "FAIL" else 0
    conn.execute(
        ss.update()
        .where(ss.c.device_id == device_id)
        .values(
            name=name or ss.c.name,
            status=status,
            barcode=barcode or "无条码",
            total=ss.c.total + 1,
            first_pass=ss.c.first_pass + first_inc,
            retest_pass=ss.c.retest_pass + retest_inc,
            fail=ss.c.fail + fail_inc,
            status_since=status_since,
            test_duration=duration_seconds,
        )
    )
    fd = engine.station_fail_detail
    for item in failed_items:
        conn.execute(
            fd.insert().values(
                device_id=device_id,
                test_item=item or "/",
                barcode=barcode or "/",
                failed_at=db.utc_now_iso(),
            )
        )


def apply_test_start(
    conn: Conn,
    *,
    device_id: str,
    name: str,
    barcode: str | None,
    status_since: int,
) -> None:
    """设备上报测试开始：状态切换为测试中，保留其他统计字段。"""
    ensure_device(conn, device_id, name)
    values = {
        "status": DEVICE_STATUS_TESTING,
        "status_since": status_since,
    }
    if barcode:
        values["barcode"] = barcode
    conn.execute(
        ss.update().where(ss.c.device_id == device_id).values(**values)
    )
