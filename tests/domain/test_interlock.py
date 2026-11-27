"""InterlockPolicy 单测：五步顺序与缺省 device_id 路径。"""

from py_server.domain.interlock.policy import InterlockPolicy, InterlockReason
from py_server.domain.trust.verdict import TrustReason, TrustVerdict
from py_server.domain.workpiece.model import Workpiece, WorkpieceStatus

TRUSTED = TrustVerdict.ok()
UNTRUSTED = TrustVerdict(False, TrustReason.NO_REPORT)


def test_device_untrusted_before_manual_release():
    wp = Workpiece(workpiece="W1", manual_release_at="2026/11/16 00:00:00.000")
    decision = InterlockPolicy.evaluate(
        workpiece=wp, device_id="D1", product="P1", trust=UNTRUSTED,
        upstreams=(), trusted_pass_upstreams=(),
    )
    assert decision.reason is InterlockReason.DEVICE_UNTRUSTED
    assert decision.allowed is False


def test_locked_before_manual_release():
    wp = Workpiece(workpiece="W1", lock_reason="锁定", manual_release_at="2026/11/16 00:00:00.000")
    decision = InterlockPolicy.evaluate(
        workpiece=wp, device_id="D1", product="P1", trust=TRUSTED,
        upstreams=(), trusted_pass_upstreams=(),
    )
    assert decision.reason is InterlockReason.WORKPIECE_LOCKED


def test_fail_before_manual_release():
    wp = Workpiece(workpiece="W1", status=WorkpieceStatus.FAIL, manual_release_at="2026/11/16 00:00:00.000")
    decision = InterlockPolicy.evaluate(
        workpiece=wp, device_id="D1", product="P1", trust=TRUSTED,
        upstreams=(), trusted_pass_upstreams=(),
    )
    assert decision.reason is InterlockReason.WORKPIECE_FAILED


def test_manual_release_allows_before_upstream_check():
    wp = Workpiece(workpiece="W1", manual_release_at="2026/11/16 00:00:00.000")
    decision = InterlockPolicy.evaluate(
        workpiece=wp, device_id="D1", product="P1", trust=TRUSTED,
        upstreams=("D0",), trusted_pass_upstreams=(),
    )
    assert decision.allowed is True
    assert decision.reason is InterlockReason.MANUAL_RELEASE
    assert decision.manual_release is True


def test_upstream_missing():
    decision = InterlockPolicy.evaluate(
        workpiece=None, device_id="D3", product="P1", trust=TRUSTED,
        upstreams=("D1", "D2"), trusted_pass_upstreams=("D1",),
    )
    assert decision.allowed is False
    assert decision.reason is InterlockReason.UPSTREAM_MISSING
    assert decision.upstream_missing == ("D2",)


def test_ok():
    decision = InterlockPolicy.evaluate(
        workpiece=None, device_id="D2", product="P1", trust=TRUSTED,
        upstreams=("D1",), trusted_pass_upstreams=("D1",),
    )
    assert decision.allowed is True
    assert decision.reason is InterlockReason.OK


def test_missing_device_id_with_no_current_device_is_untrusted():
    decision = InterlockPolicy.evaluate(
        workpiece=None, device_id=None, product="P1", trust=UNTRUSTED,
        upstreams=(), trusted_pass_upstreams=(),
    )
    assert decision.allowed is False
    assert decision.reason is InterlockReason.MISSING_DEVICE_ID
    assert "device_id" in decision.detail


def test_module_is_framework_free():
    """domain/ 的模块不能 import sqlalchemy / fastapi / streamlit。"""
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "src" / "py_server" / "domain"
    forbidden = {"sqlalchemy", "fastapi", "streamlit", "sqlite3"}
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in forbidden, path
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden, path
