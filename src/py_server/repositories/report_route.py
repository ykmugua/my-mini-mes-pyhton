"""上报路由：根据 station 找到工序测试库。"""

from __future__ import annotations

from .. import engine as eg
from .base import Conn, with_read_conn


def step_for_station(station: str, conn: Conn | None = None) -> dict | None:
    """设备表不再维护工序；该接口保留兼容返回值，但始终返回 None。"""
    if conn is None:
        with with_read_conn() as c:
            return step_for_station(station, c)
    return None


def report_engine_for_station(station: str, conn: Conn | None = None):
    """按 station 获取对应工序测试库 Engine；未注册设备回退到默认 TestReport.db。"""
    info = step_for_station(station, conn)
    if info is None or not info.get("step_name"):
        return eg.get_details_engine()
    return eg.get_report_engine(info["step_no"])
