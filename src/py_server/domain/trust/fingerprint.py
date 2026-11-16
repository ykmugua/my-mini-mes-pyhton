"""程序指纹与来源。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FingerprintSource(str, Enum):
    TEST_RESULT = "TEST_RESULT"   # 测试结果自带字段，优先级最高
    STATUS_REPORT = "STATUS_REPORT"  # 设备最近一次 /api/program/status 上报
    NONE = "NONE"


@dataclass(frozen=True)
class ProgramFingerprint:
    version: str | None
    sha256: str | None
    source: FingerprintSource

    @property
    def present(self) -> bool:
        return bool(self.version) or bool(self.sha256)