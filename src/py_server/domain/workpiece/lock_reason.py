"""锁定原因值对象。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class LockReasonCode(str, Enum):
    UNTRUSTED_RESULT = "UNTRUSTED_RESULT"  # 测试结果不可信
    FAIL_RESULT = "FAIL_RESULT"            # 测试判定 FAIL
    MANUAL = "MANUAL"                      # 人工锁定


@dataclass(frozen=True)
class LockReason:
    code: LockReasonCode
    detail: str

    def __str__(self) -> str:
        return f"{self.detail}（{self.code.value}）" if self.code != LockReasonCode.MANUAL else self.detail