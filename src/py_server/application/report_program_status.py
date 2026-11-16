"""用例：设备上报程序状态（含检出/异常时的落盘）。"""

from __future__ import annotations

from typing import Any

from .. import db
from ..domain.trust.binding import Binding
from ..repositories import binding_repo
from ..repositories.base import with_conn


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