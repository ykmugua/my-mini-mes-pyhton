"""测试数据看板统计时间区间的规则测试。"""

from __future__ import annotations

from datetime import datetime

from py_server.ui import page_dashboard


def test_effective_stat_range_default_uses_now_each_call(monkeypatch):
    """默认模式每次调用都取新的当前时间，不固化结束时间。"""
    monkeypatch.setattr(page_dashboard.st, "session_state", {})
    first = datetime(2026, 11, 25, 10, 0, 0)
    second = datetime(2026, 11, 25, 10, 0, 1)

    monkeypatch.setattr(page_dashboard, "datetime", type(
        "FixedDateTime",
        (),
        {"now": staticmethod(lambda: first)},
    ))
    start, end = page_dashboard._effective_stat_range()
    assert start == first.replace(hour=0, minute=0, second=0, microsecond=0)
    assert end == first

    monkeypatch.setattr(page_dashboard, "datetime", type(
        "FixedDateTime",
        (),
        {"now": staticmethod(lambda: second)},
    ))
    start, end = page_dashboard._effective_stat_range()
    assert start == second.replace(hour=0, minute=0, second=0, microsecond=0)
    assert end == second


def test_apply_stat_range_fills_missing_custom_bound(monkeypatch):
    """自定义模式只填开始时间时，结束时间保持动态 now。"""
    now = datetime(2026, 11, 25, 14, 30, 0)
    state = {
        "stat_time_start": now,
        "stat_time_end": None,
    }
    monkeypatch.setattr(page_dashboard.st, "session_state", state)

    real_datetime = page_dashboard.datetime

    class FixedDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(page_dashboard, "datetime", FixedDateTime)

    page_dashboard._apply_stat_range()
    start, end = page_dashboard._effective_stat_range()
    assert state["stat_range_mode"] == "custom"
    assert start == now
    assert end is None
