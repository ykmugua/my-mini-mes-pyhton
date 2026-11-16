"""用例：测试结果上报（幂等 → 聚合变更 → 落盘，同一事务内完成）。"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from .. import config, db
from ..domain.trust.binding import Binding
from ..domain.trust.policy import ProgramTrustPolicy
from ..domain.workpiece.model import WorkpieceStatus
from ..repositories import binding_repo, workpiece_repo
from ..repositories.base import with_conn


def evaluate_trust(
    conn,
    *,
    device_id: str,
    product: str | None,
    reported_version: str | None,
    reported_sha256: str | None,
) -> tuple[bool, str, Any | None]:
    """用纯领域策略计算可信性，返回 (trusted, detail, binding_row)。

    保留既有中文 detail 文案以兼容接口/看板断言。
    """
    if not product and binding_repo.binding_count(conn, device_id) > 1:
        return (
            False,
            f"设备 {device_id} 绑定多个产品，无法确定程序版本，请指定 product",
            None,
        )
    binding_row = binding_repo.try_binding(conn, device_id, product)
    if binding_row is None:
        return False, f"设备 {device_id} 未配置程序绑定", None

    binding = Binding.from_row(binding_row)
    verdict = ProgramTrustPolicy.evaluate(
        binding=binding,
        reported_version=reported_version,
        reported_sha256=reported_sha256,
    )
    if verdict.trusted:
        return True, "", binding_row

    # detail 文案按判定顺序拼装，保持与旧实现一致
    fp = ProgramTrustPolicy.merge_fingerprint(reported_version, reported_sha256, binding)
    version = fp.version or ""
    sha = fp.sha256 or ""
    reasons: list[str] = []
    if not version:
        reasons.append("设备未上报程序版本")
    elif version != binding.program_version:
        reasons.append(f"程序版本 {version} 与绑定版本 {binding.program_version} 不一致")
    if not sha:
        reasons.append("设备未上报程序校验和")
    elif sha != binding.sha256.lower():
        reasons.append("程序校验和与绑定不一致")
    if binding.self_check_failed:
        reasons.append("设备最近一次程序校验失败")
    return False, "；".join(reasons), binding_row


def execute(
    *,
    workpiece: str,
    device_id: str,
    test_item: str,
    result: str,
    measured_text: str,
    tested_at_iso: str,
    now: str,
    parsed_tested_at,
    tested_at_adjusted: bool,
    product: str | None,
    program_version: str | None,
    program_sha256: str | None,
    ValidationError,
    ConflictError,
) -> dict:
    """事务：幂等检查 → 可信性判定 → 工件状态变更 → 写 test_results。"""
    with with_conn() as conn:
        existing_wp = workpiece_repo.get_workpiece(conn, workpiece)
        requested_product = str(product).strip() if product else ""
        if (
            existing_wp
            and existing_wp["product"]
            and requested_product
            and requested_product != existing_wp["product"]
        ):
            raise ValidationError(
                f"工件 {workpiece} 已属于产品 {existing_wp['product']}，"
                f"不能以产品 {requested_product} 上报结果"
            )

        workpiece_repo.insert_workpiece_ignore(
            conn, workpiece=workpiece, product=product or None, now=now
        )
        wp = workpiece_repo.get_workpiece(conn, workpiece)
        # 解析产品（工件自带产品优先，其次显式入参，最后设备唯一绑定）
        resolved_product = requested_product or (wp["product"] if wp else "")
        if not resolved_product:
            products = binding_repo.binding_products(conn, device_id)
            if len(products) == 1:
                resolved_product = products[0]

        if wp and not wp["product"] and resolved_product:
            workpiece_repo.set_workpiece_product(conn, workpiece, resolved_product, now)

        trusted, untrusted_reason, binding = evaluate_trust(
            conn,
            device_id=device_id,
            product=resolved_product or None,
            reported_version=program_version,
            reported_sha256=program_sha256,
        )
        if binding and not resolved_product:
            resolved_product = binding["product"]

        rowcount = workpiece_repo.insert_test_result_ignore(
            conn,
            {
                "workpiece": workpiece,
                "device_id": device_id,
                "product": resolved_product or None,
                "program_version": program_version
                or (binding["reported_version"] if binding else None),
                "program_sha256": program_sha256
                or (binding["reported_sha256"] if binding else None),
                "test_item": test_item,
                "measured_value": measured_text,
                "result": result,
                "tested_at": tested_at_iso,
                "reported_at": now,
                "trusted": 1 if trusted else 0,
                "untrusted_reason": untrusted_reason or None,
            },
        )
        duplicate = rowcount == 0
        if duplicate:
            row = workpiece_repo.get_test_result(conn, workpiece, device_id, test_item)
            if row["result"] != result:
                raise ConflictError(
                    f"工件 {workpiece} 在设备 {device_id} 的测试项 {test_item} 已记录 "
                    f"{row['result']}，本次上报 {result} 与已有结果冲突。"
                    "同一测试项只记录一次；如需复测请使用新的测试项名称。"
                )
            return {
                "accepted": True,
                "duplicate": True,
                "stale": False,
                "id": row["id"],
                "workpiece": workpiece,
                "device_id": device_id,
                "test_item": test_item,
                "result": row["result"],
                "trusted": bool(row["trusted"]),
                "untrusted_reason": row["untrusted_reason"],
                "workpiece_status": workpiece_repo.public_workpiece(conn, workpiece),
            }

        # 新插入的行 id：通过查询唯一键取得（SQLAlchemy 不保证批量 insert 的 lastrowid）
        inserted = workpiece_repo.get_test_result(conn, workpiece, device_id, test_item)
        new_id = inserted["id"]

        # 离线补传：只入库，不覆盖更新的工件状态
        latest = workpiece_repo.latest_tested_at(conn, workpiece, new_id)
        stale = False
        latest_dt = db.parse_ts(latest)
        if latest_dt is not None:
            tolerance = timedelta(seconds=config.stale_tolerance_seconds())
            stale = parsed_tested_at < latest_dt - tolerance

        if stale:
            pass
        elif not trusted:
            workpiece_repo.lock_workpiece(
                conn,
                workpiece=workpiece,
                device_id=device_id,
                reason=f"测试结果不可信（{untrusted_reason}）",
                now=now,
            )
        elif result == "FAIL":
            workpiece_repo.fail_workpiece(
                conn,
                workpiece=workpiece,
                device_id=device_id,
                reason=f"测试项 {test_item} 判定 FAIL（设备 {device_id}）",
                now=now,
            )
        else:
            workpiece_repo.pass_workpiece(
                conn, workpiece=workpiece, device_id=device_id, now=now
            )

        return {
            "accepted": True,
            "duplicate": False,
            "stale": stale,
            "latest_tested_at": latest,
            "tested_at_adjusted": tested_at_adjusted,
            "tested_at": tested_at_iso,
            "id": new_id,
            "workpiece": workpiece,
            "device_id": device_id,
            "test_item": test_item,
            "result": result,
            "trusted": trusted,
            "untrusted_reason": untrusted_reason or None,
            "workpiece_status": workpiece_repo.public_workpiece(conn, workpiece),
        }