"""用例：设备上报程序状态（含检出/异常时的落盘）。"""

from __future__ import annotations

from typing import Any

from .. import db
from ..domain.trust.binding import Binding
from ..domain.trust.policy import ProgramTrustPolicy
from ..domain.trust.verdict import TrustReason
from ..repositories import binding_repo
from ..repositories.base import with_conn


def evaluate_program_status(
    *,
    binding: dict | None,
    binding_count: int,
    product: str | None,
    reported_version: str | None,
    reported_sha256: str | None,
    sha256_ok: bool | None,
) -> tuple[bool, list[str], str]:
    """用领域策略判定程序状态，并保留既有中文 detail 文案。"""
    version = (reported_version or "").strip()
    sha = (reported_sha256 or "").strip().lower()
    if binding is None:
        reason = (
            "设备绑定多个产品，请指定 product"
            if binding_count > 1 and not product
            else "设备未配置程序绑定"
        )
        return False, [reason], product or ""

    domain_binding = Binding.from_row(binding)
    verdict = ProgramTrustPolicy.evaluate(
        binding=domain_binding,
        reported_version=reported_version,
        reported_sha256=reported_sha256,
        self_check_failed=sha256_ok is False,
    )
    if verdict.trusted:
        return True, [], str(binding["product"])

    reasons: list[str] = []
    if not version:
        reasons.append("未上报程序版本")
    elif version != str(binding["program_version"]):
        reasons.append(
            f"上报版本 {version} 与绑定版本 {binding['program_version']} 不一致"
        )
    if not sha:
        reasons.append("未上报程序 SHA256")
    elif sha != str(binding["sha256"]).lower():
        reasons.append("上报校验和与绑定校验和不一致")
    if verdict.reason is TrustReason.SELF_CHECK_FAILED:
        reasons.append("设备自检校验和不匹配")
    return False, reasons, str(binding["product"])


def execute(
    *,
    device_id: str,
    product: str | None,
    reported_version: str | None,
    reported_sha256: str | None,
    sha256_ok: bool | None,
    # 由 services 层完成清洗/判定后传入的最终值
    binding: dict | None,
    binding_count: int,
    reasons: list[str],
    trusted: bool,
    resolved_product: str,
    version: str,
    sha: str,
    now: str,
) -> dict:
    """用例持有事务：更新绑定上报字段 + 写程序状态日志。"""
    with with_conn() as conn:
        if binding is not None:
            binding_repo.update_reported_status(
                conn,
                binding["id"],
                version=version or None,
                sha=sha or None,
                reported_at=now,
                program_ok=1 if trusted else 0,
                now=now,
            )
        binding_repo.insert_status_log(
            conn,
            {
                "device_id": device_id,
                "product": resolved_product or None,
                "reported_version": version or None,
                "reported_sha256": sha or None,
                "sha256_ok": None if sha256_ok is None else (1 if sha256_ok else 0),
                "trusted": 1 if trusted else 0,
                "reason": "；".join(reasons) or None,
                "reported_at": now,
            },
        )
        return {
            "device_id": device_id,
            "product": resolved_product or None,
            "trusted": trusted,
            "can_produce": trusted,
            "reason": "；".join(reasons),
            "binding_version": binding["program_version"] if binding else None,
            "binding_sha256": binding["sha256"] if binding else None,
            "reported_version": version or None,
            "reported_sha256": sha or None,
            "checked_at": now,
        }
