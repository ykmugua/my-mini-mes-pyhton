"""人工放行记录值对象。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ManualReleaseRecord:
    workpiece: str
    operator: str
    reason: str
    device_id: str | None
    lock_reason: str
    unlocked_at: str