"""用例：人工解锁工件（聚合返回 UnlockOutcome，用例写 unlock_logs）。"""

from __future__ import annotations

from .. import db
from ..domain.workpiece.model import Workpiece
from ..repositories import log_repo, workpiece_repo
from ..repositories.base import with_conn


def execute(*, wp_row, operator: str, reason: str, confirmed: bool, now: str) -> dict:
    """事务边界：校验 → 聚合 unlock → 写日志 → 更新工件。"""
    from ..domain import InvariantViolation

    wp = Workpiece.from_row(wp_row)
    # 空原因/未确认/未锁定的领域校验在聚合内完成，不写库
    outcome = wp.unlock(operator=operator, reason=reason, confirmed=confirmed, now=now)

    with with_conn() as conn:
        log_repo.insert_unlock_log(
            conn,
            {
                "workpiece": outcome.workpiece,
                "operator": operator,
                "reason": reason,
                "device_id": wp.current_device,
                "lock_reason": outcome.previous_lock_reason,
                "unlocked_at": now,
            },
        )
        workpiece_repo.unlock_workpiece_row(
            conn,
            workpiece=outcome.workpiece,
            operator=operator,
            reason=reason,
            now=now,
        )
        data = workpiece_repo.public_workpiece(conn, outcome.workpiece)
        data["previous_lock_reason"] = outcome.previous_lock_reason
        data["unlock_log"] = {
            "workpiece": outcome.workpiece,
            "operator": operator,
            "reason": reason,
            "unlocked_at": now,
        }
        return data