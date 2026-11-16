"""可信性判定结果。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TrustReason(str, Enum):
    NOT_BOUND = "NOT_BOUND"
    NO_REPORT = "NO_REPORT"
    SELF_CHECK_FAILED = "SELF_CHECK_FAILED"
    INCOMPLETE_REPORT = "INCOMPLETE_REPORT"
    VERSION_MISMATCH = "VERSION_MISMATCH"
    SHA_MISMATCH = "SHA_MISMATCH"
    OK = "OK"


@dataclass(frozen=True)
class TrustVerdict:
    trusted: bool
    reason: TrustReason
    reasons: tuple[TrustReason, ...] = ()
    detail: str = ""

    @classmethod
    def ok(cls) -> "TrustVerdict":
        return cls(trusted=True, reason=TrustReason.OK)