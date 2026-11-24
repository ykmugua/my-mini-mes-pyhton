"""InterlockPolicy：严格五步顺序，短路返回；纯领域逻辑，不访问数据库。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..trust.verdict import TrustVerdict
from ..workpiece.model import Workpiece


class InterlockReason(str, Enum):
    """InterlockReason 类。"""
    DEVICE_UNTRUSTED = "DEVICE_UNTRUSTED"
    WORKPIECE_LOCKED = "WORKPIECE_LOCKED"
    WORKPIECE_FAILED = "WORKPIECE_FAILED"
    PRODUCT_MISMATCH = "PRODUCT_MISMATCH"
    MISSING_DEVICE_ID = "MISSING_DEVICE_ID"
    MANUAL_RELEASE = "MANUAL_RELEASE"
    UPSTREAM_MISSING = "UPSTREAM_MISSING"
    OK = "OK"


@dataclass(frozen=True)
class InterlockDecision:
    """InterlockDecision 类。"""
    allowed: bool
    reason: InterlockReason
    detail: str = ""
    upstream_missing: tuple[str, ...] = ()
    manual_release: bool = False


class InterlockPolicy:
    """设备不可信优先于人工解锁；缺 device_id 直接拒绝。"""

    @classmethod
    def evaluate(
        cls,
        *,
        workpiece: Workpiece | None,
        device_id: str | None,
        product: str | None,
        trust: TrustVerdict,
        upstreams: tuple[str, ...],
        trusted_pass_upstreams: tuple[str, ...],
        trust_detail: str = "",
        product_mismatch: str = "",
    ) -> InterlockDecision:
        # device_id 省略且工件无最近设备 → 直接 DEVICE_UNTRUSTED
        """执行 evaluate。"""
        if not device_id:
            return InterlockDecision(
                False,
                InterlockReason.MISSING_DEVICE_ID,
                "缺少 device_id，无法判定本设备的程序可信性与前道放行条件",
            )

        if product_mismatch:
            return InterlockDecision(
                False,
                InterlockReason.PRODUCT_MISMATCH,
                product_mismatch,
            )

        # 第一步：设备程序可信？——必须在解锁之前
        if not trust.trusted:
            return InterlockDecision(
                False,
                InterlockReason.DEVICE_UNTRUSTED,
                f"设备程序不可信：{trust_detail or trust.reason.value}",
            )

        # 第二步：工件未锁定？
        if workpiece and workpiece.locked:
            return InterlockDecision(
                False, InterlockReason.WORKPIECE_LOCKED, workpiece.lock_reason or "工件已锁定"
            )

        # 第三步：工件非 FAIL？
        if workpiece and workpiece.status.value == "FAIL":
            return InterlockDecision(
                False, InterlockReason.WORKPIECE_FAILED, "工件存在 FAIL 记录，已锁定"
            )

        # 第四步：存在人工放行记录 → 允许
        if workpiece and workpiece.manual_release_at:
            return InterlockDecision(
                True, InterlockReason.MANUAL_RELEASE, "人工解锁放行", manual_release=True
            )

        # 第五步：前道关键设备均有可信 PASS
        passed = set(trusted_pass_upstreams)
        missing = tuple(up for up in upstreams if up not in passed)
        if missing:
            return InterlockDecision(
                False,
                InterlockReason.UPSTREAM_MISSING,
                "前道关键设备无 PASS 记录：" + "、".join(missing),
                upstream_missing=missing,
            )

        return InterlockDecision(True, InterlockReason.OK)