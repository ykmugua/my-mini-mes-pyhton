"""程序可信性策略单测：六种 TrustReason + 指纹优先级三 case。"""

from py_server.domain.trust.binding import Binding
from py_server.domain.trust.fingerprint import FingerprintSource
from py_server.domain.trust.policy import ProgramTrustPolicy
from py_server.domain.trust.verdict import TrustReason

SHA = "a" * 64


def _binding(**overrides) -> Binding:
    values = dict(
        device_id="D1",
        product="P1",
        program_version="v1",
        download_url="http://x/a.bin",
        sha256=SHA,
    )
    values.update(overrides)
    return Binding(**values)


def test_not_bound():
    verdict = ProgramTrustPolicy.evaluate(binding=None)
    assert verdict.reason is TrustReason.NOT_BOUND
    assert verdict.trusted is False


def test_no_report():
    verdict = ProgramTrustPolicy.evaluate(binding=_binding())
    assert verdict.reason is TrustReason.NO_REPORT


def test_self_check_failed_takes_priority():
    verdict = ProgramTrustPolicy.evaluate(
        binding=_binding(program_ok=0, reported_version="v1", reported_sha256=SHA),
    )
    assert verdict.reason is TrustReason.SELF_CHECK_FAILED


def test_incomplete_report_when_version_missing():
    verdict = ProgramTrustPolicy.evaluate(
        binding=_binding(), reported_version=None, reported_sha256=SHA
    )
    assert verdict.reason is TrustReason.INCOMPLETE_REPORT


def test_version_mismatch():
    verdict = ProgramTrustPolicy.evaluate(
        binding=_binding(), reported_version="v0", reported_sha256=SHA
    )
    assert verdict.reason is TrustReason.VERSION_MISMATCH
    assert TrustReason.VERSION_MISMATCH in verdict.reasons


def test_sha_mismatch():
    verdict = ProgramTrustPolicy.evaluate(
        binding=_binding(), reported_version="v1", reported_sha256="b" * 64
    )
    assert verdict.reason is TrustReason.SHA_MISMATCH


def test_both_mismatch_lists_all_reasons():
    verdict = ProgramTrustPolicy.evaluate(
        binding=_binding(), reported_version="v0", reported_sha256="b" * 64
    )
    assert verdict.trusted is False
    assert verdict.reasons == (TrustReason.VERSION_MISMATCH, TrustReason.SHA_MISMATCH)


def test_ok():
    verdict = ProgramTrustPolicy.evaluate(
        binding=_binding(), reported_version="v1", reported_sha256=SHA
    )
    assert verdict.trusted is True
    assert verdict.reason is TrustReason.OK


# --- 指纹优先级三 case ---
def test_fingerprint_only_test_result_fields():
    binding = _binding(reported_version="old", reported_sha256="b" * 64)
    fp = ProgramTrustPolicy.merge_fingerprint("v1", SHA, binding)
    assert fp.source is FingerprintSource.TEST_RESULT
    assert fp.version == "v1"
    assert fp.sha256 == SHA


def test_fingerprint_only_status_report():
    binding = _binding(reported_version="v1", reported_sha256=SHA)
    fp = ProgramTrustPolicy.merge_fingerprint(None, None, binding)
    assert fp.source is FingerprintSource.STATUS_REPORT
    assert fp.version == "v1"


def test_fingerprint_test_result_wins_when_both_present_and_conflict():
    binding = _binding(reported_version="status-version", reported_sha256="b" * 64)
    fp = ProgramTrustPolicy.merge_fingerprint("test-version", "c" * 64, binding)
    assert fp.source is FingerprintSource.TEST_RESULT
    assert fp.version == "test-version"
    assert fp.sha256 == "c" * 64

    verdict = ProgramTrustPolicy.evaluate(
        binding=binding, reported_version="test-version", reported_sha256="c" * 64
    )
    assert verdict.reason is TrustReason.VERSION_MISMATCH