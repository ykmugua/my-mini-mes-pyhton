"""用例：工件解锁（mes.db 工件锁 + ProductFlow 流转锁）。"""

from __future__ import annotations

from .. import db
from ..domain import InvariantViolation
from ..domain.workpiece.model import Workpiece, UnlockOutcome
from ..repositories import log_repo, product_flow_store, report_route, workpiece_repo
from ..repositories.base import with_conn


def execute(*, wp_row, operator: str, reason: str, confirmed: bool, now: str, target_step=None, note=None) -> dict:
    """事务边界：校验 → 解锁（如有）→ 写流转库。"""
    wp = Workpiece.from_row(wp_row)

    if not reason or not reason.strip():
        raise InvariantViolation("解锁原因不能为空")
    if not confirmed:
        raise InvariantViolation("必须勾选确认后才能解锁")

    # 仅当显式指定 target_step 且 mes.db 工件未锁时，才按“流转锁”处理；
    # 否则保持原有业务规则：未锁工件不可重复解锁。
    flow_only = (not wp.locked) and bool(target_step)
    if flow_only:
        outcome = UnlockOutcome(
            workpiece=wp.workpiece,
            previous_lock_reason="ProductFlow lock",
            operator=operator,
            reason=reason,
            device_id=wp.current_device,
            unlocked_at=now,
        )
    else:
        outcome = wp.unlock(operator=operator, reason=reason, confirmed=confirmed, now=now)

    with with_conn() as conn:
        if not flow_only:
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

        # 写产品流转库：手动解锁
        info = report_route.step_for_station(wp.current_device or "", conn)
        product_flow_store.upsert_flow(
            barcode=outcome.workpiece,
            componentcode=wp_row.get("product") or "",
            board_status="normal",
            step_no=str(target_step) if target_step else ((info or {}).get("step_no") or ""),
            next_step="",
            line_id=(info or {}).get("line_id") or "",
            device="手动解锁",
            note=(note or reason or "unlock"),
            changed_at=now,
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
