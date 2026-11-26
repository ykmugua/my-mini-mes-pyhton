"""程序可信性判定策略：短路返回，纯领域逻辑。"""

from __future__ import annotations

from .binding import Binding
from .fingerprint import FingerprintSource, ProgramFingerprint
from .verdict import TrustReason, TrustVerdict


class ProgramTrustPolicy:
    """纯策略类：不访问数据库、不写日志、不依赖任何框架。"""

    @staticmethod
    def merge_fingerprint(
        reported_version: str | None,
        reported_sha256: str | None,
        binding: Binding,
    ) -> ProgramFingerprint:
        """指纹优先级：测试结果字段 > status 上报；两者都无则 NONE。"""
        version = (reported_version or "").strip()
        sha = (reported_sha256 or "").strip().lower()
        if version or sha:
            return ProgramFingerprint(
                version=version or None,
                sha256=sha or None,
                source=FingerprintSource.TEST_RESULT,
            )
        version = (binding.reported_version or "").strip()
        sha = (binding.reported_sha256 or "").strip().lower()
        if version or sha:
            return ProgramFingerprint(
                version=version or None,
                sha256=sha or None,
                source=FingerprintSource.STATUS_REPORT,
            )
        return ProgramFingerprint(version=None, sha256=None, source=FingerprintSource.NONE)

    @classmethod
    def evaluate(
        cls,
        *,
        binding: Binding | None,
        reported_version: str | None = None,
        reported_sha256: str | None = None,
        self_check_failed: bool | None = None,
    ) -> TrustVerdict:
        """按铁律顺序短路判定。"""
        if binding is None:
            return TrustVerdict(False, TrustReason.NOT_BOUND)

        fingerprint = cls.merge_fingerprint(reported_version, reported_sha256, binding)
        if fingerprint.source is FingerprintSource.NONE:
            return TrustVerdict(False, TrustReason.NO_REPORT)

        failed = binding.self_check_failed if self_check_failed is None else self_check_failed
        if failed:
            return TrustVerdict(False, TrustReason.SELF_CHECK_FAILED)

        if not fingerprint.version or not fingerprint.sha256:
            return TrustVerdict(False, TrustReason.INCOMPLETE_REPORT)

        reasons: list[TrustReason] = []
        if fingerprint.version != binding.program_version:
            reasons.append(TrustReason.VERSION_MISMATCH)
        if fingerprint.sha256 != binding.sha256.lower():
            reasons.append(TrustReason.SHA_MISMATCH)
        if reasons:
            return TrustVerdict(
                False, reasons[0], tuple(reasons)
            )
        return TrustVerdict.ok()
