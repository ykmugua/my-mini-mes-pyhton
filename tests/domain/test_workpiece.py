"""Workpiece 聚合单测：unlock 回 PENDING、LOCKED 不可 mark_pass、空原因拒绝、不写库。"""

import pytest

from py_server.domain import InvariantViolation
from py_server.domain.workpiece.model import Workpiece, WorkpieceStatus


def _locked() -> Workpiece:
    return Workpiece(
        workpiece="W1",
        status=WorkpieceStatus.FAIL,
        lock_reason="测试项 绝缘 FAIL",
        locked_at="2026-11-16T00:00:00+00:00",
        current_device="D2",
    )


def test_unlock_returns_pending_and_outcome():
    wp = _locked()
    outcome = wp.unlock(operator="张工", reason="返修确认", confirmed=True, now="2026-11-16T01:00:00+00:00")
    assert wp.status is WorkpieceStatus.PENDING
    assert wp.lock_reason is None
    assert wp.manual_release_at == "2026-11-16T01:00:00+00:00"
    assert outcome.workpiece == "W1"
    assert outcome.previous_lock_reason == "测试项 绝缘 FAIL"
    assert outcome.operator == "张工"
    assert outcome.device_id == "D2"


def test_locked_cannot_mark_pass():
    wp = _locked()
    with pytest.raises(InvariantViolation):
        wp.mark_pass()


def test_empty_reason_rejected():
    wp = _locked()
    with pytest.raises(InvariantViolation):
        wp.unlock(operator="张工", reason="   ", confirmed=True)


def test_unconfirmed_rejected():
    wp = _locked()
    with pytest.raises(InvariantViolation):
        wp.unlock(operator="张工", reason="确认", confirmed=False)


def test_aggregate_does_not_write_logs():
    wp = _locked()
    assert wp.pending_events == []
    wp.unlock(operator="张工", reason="确认", confirmed=True)
    # 聚合只返回 UnlockOutcome，不持有任何待写库日志列表
    assert wp.pending_events == []


def test_mark_pass_on_unlocked():
    wp = Workpiece(workpiece="W2")
    wp.mark_pass()
    assert wp.status is WorkpieceStatus.PASS