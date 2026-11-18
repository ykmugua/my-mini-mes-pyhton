"""上报路由：根据 station 找到工序测试库。"""

from __future__ import annotations

from .. import engine as eg
from .base import Conn, with_read_conn


def step_for_station(station: str, conn: Conn | None = None) -> dict | None:
    """查设备所属工序、线体、工序名（英文/数字）。"""
    if conn is None:
        with with_read_conn() as c:
            return step_for_station(station, c)
    from sqlalchemy import text

    row = conn.execute(text(
        "SELECT d.device_id, d.line_id, d.step_no, s.step_name "
        "FROM devices d LEFT JOIN steps s ON d.step_no = s.step_no "
        "WHERE d.device_id = :st"
    ), {"st": station}).fetchone()
    if row is None:
        return None
    m = dict(row)
    return {
        "device_id": m["device_id"],
        "line_id": m["line_id"],
        "step_no": m["step_no"],
        "step_name": m["step_name"],
    }


def report_engine_for_station(station: str, conn: Conn | None = None):
    """按 station 获取对应工序测试库 Engine；未注册设备回退到默认 TestReport.db。"""
    info = step_for_station(station, conn)
    if info is None or not info.get("step_name"):
        return eg.get_details_engine()
    return eg.get_report_engine(info["step_no"], info["step_name"])
