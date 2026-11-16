"""Workpiece 聚合：只做状态判定与状态变更，不写库、不记日志。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from .. import InvariantViolation


class WorkpieceStatus(str, Enum):
    PENDING = "PENDING"
    PASS = "PASS"
    FAIL = "FAIL"


@dataclass(frozen=True)
class UnlockOutcome:
    """待持久化事实：聚合不写库，由 application 用例在同一事务内落盘。"""

    workpiece: str
    previous_lock_reason: str
    operator: str
    reason: str
    device_id: str | None
    unlocked_at: str
    status: WorkpieceStatus = WorkpieceStatus.PENDING


@dataclass
class Workpiece:
    workpiece: str
    product: str | None = None
    current_device: str | None = None
    status: WorkpieceStatus = WorkpieceStatus.PENDING
    lock_reason: str | None = None
    locked_at: str | None = None
    lock_device: str | None = None
    unlock_by: str | None = None
    unlock_reason: str | None = None
    unlocked_at: str | None = None
    manual_release_at: str | None = None
    pending_events: list[Any] = field(default_factory=list, repr=False)

    @classmethod
    def from_row(cls, row) -> "Workpiece":
        data = dict(row)
        status = data.get("status")
        return cls(
            workpiece=data["workpiece"],
            product=data.get("product"),
            current_device=data.get("current_device"),
            status=WorkpieceStatus(status) if status else WorkpieceStatus.PENDING,
            lock_reason=data.get("lock_reason"),
            locked_at=data.get("locked_at"),
            lock_device=data.get("lock_device"),
            unlock_by=data.get("unlock_by"),
            unlock_reason=data.get("unlock_reason"),
            unlocked_at=data.get("unlocked_at"),
            manual_release_at=data.get("manual_release_at"),
        )

    @property
    def locked(self) -> bool:
        return bool(self.lock_reason)

    def mark_pass(self) -> None:
        """PASS 推进：LOCKED 状态禁止直接 mark_pass，必须走 unlock。"""
        if self.locked:
            raise InvariantViolation(
                f"工件 {self.workpiece} 已锁定，不能直接标记 PASS，必须先解锁"
            )
        self.status = WorkpieceStatus.PASS

    def mark_fail(self, *, device_id: str, reason: str, now: str) -> None:
        """FAIL 推进：同时给工件上锁。"""
        self.status = WorkpieceStatus.FAIL
        self.current_device = device_id
        self.lock_reason = reason
        self.locked_at = now
        self.lock_device = device_id

    def lock(self, *, device_id: str | None, reason: str, now: str) -> None:
        """不可信结果只上锁，不改变 status。"""
        if not self.lock_reason:
            self.lock_reason = reason
            self.locked_at = now
            self.lock_device = device_id

    def unlock(self, *, operator: str, reason: str, confirmed: bool, now: str | None = None) -> UnlockOutcome:
        """人工解锁：原因必填、必须勾选确认；返回待持久化事实，不写库。"""
        if not reason or not reason.strip():
            raise InvariantViolation("解锁原因不能为空")
        if not confirmed:
            raise InvariantViolation("必须勾选确认后才能解锁")
        if not self.locked:
            raise InvariantViolation(f"工件 {self.workpiece} 当前未处于锁定状态")

        previous = self.lock_reason or ""
        timestamp = now or datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.status = WorkpieceStatus.PENDING
        self.lock_reason = None
        self.locked_at = None
        self.lock_device = None
        self.unlock_by = operator
        self.unlock_reason = reason
        self.unlocked_at = timestamp
        self.manual_release_at = timestamp
        return UnlockOutcome(
            workpiece=self.workpiece,
            previous_lock_reason=previous,
            operator=operator,
            reason=reason,
            device_id=self.current_device,
            unlocked_at=timestamp,
        )