"""接口与业务规则的补充测试。"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from py_server import config, db, services
from tests.helpers import SHA_A, SHA_B, push_result


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_program_unknown_device_returns_404(client, bench):
    response = client.get("/api/program", params={"device_id": "D9", "product": "P1"})
    assert response.status_code == 404


def test_program_without_product_when_unique(client, bench):
    response = client.get("/api/program", params={"device_id": "D1"})
    assert response.status_code == 200
    assert response.json()["product"] == "P1"


def test_program_ambiguous_product_returns_400(client, bench):
    services.upsert_binding(
        "D1", "P2", "v9", "http://testserver/programs/D1_p2.bin", SHA_B
    )
    response = client.get("/api/program", params={"device_id": "D1"})
    assert response.status_code == 400
    assert "product" in response.json()["detail"]


def test_program_status_unknown_device_is_untrusted(client):
    response = client.post(
        "/api/program/status",
        json={"device_id": "D9", "program_version": "v1", "sha256": SHA_A, "sha256_ok": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["trusted"] is False
    assert body["can_produce"] is False


def test_program_file_publish_and_download(client, bench):
    result = services.publish_program_file(
        "D1", "P1", "v3", "fw.bin", b"hello-program-bytes"
    )
    filename = Path(result["stored_path"]).name
    response = client.get(f"/programs/{filename}")
    assert response.status_code == 200
    assert response.content == b"hello-program-bytes"

    missing = client.get("/programs/not-exists.bin")
    assert missing.status_code == 404


def test_invalid_test_result_payload(client, bench):
    response = client.post(
        "/api/test-result",
        json={
            "workpiece": "W1",
            "device_id": "D1",
            "test_item": "电压",
            "result": "MAYBE",
        },
    )
    assert response.status_code == 422


def test_test_result_can_omit_program_fields(client, bench):
    """设备未在结果中带版本/校验和时，使用 /api/program/status 最近上报的信息。"""
    response = client.post(
        "/api/test-result",
        json={
            "workpiece": "W1",
            "device_id": "D1",
            "test_item": "电压",
            "result": "PASS",
        },
    )
    assert response.status_code == 200
    assert response.json()["trusted"] is True


def test_test_result_aliases(client, bench):
    response = client.post(
        "/api/test-result",
        json={
            "workpiece_code": "W-ALIAS",
            "device_id": "D1",
            "test_item": "电压",
            "result": "pass",
            "timestamp": "2026-11-11 10:00:00",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["result"] == "PASS"
    assert body["trusted"] is True


def test_interlock_devices_without_binding_or_bad_program(client, bench):
    unknown = client.get(
        "/api/interlock", params={"workpiece": "W1", "device_id": "D9"}
    ).json()
    assert unknown["allowed"] is False
    assert "未配置程序绑定" in unknown["reason"]

    client.post(
        "/api/program/status",
        json={
            "device_id": "D2",
            "product": "P1",
            "program_version": "v1",
            "sha256": SHA_B,
            "sha256_ok": False,
        },
    )
    bad = client.get("/api/interlock", params={"workpiece": "W1", "device_id": "D2"}).json()
    assert bad["allowed"] is False
    assert "不可信" in bad["reason"]


def test_interlock_unknown_workpiece_without_upstream_allowed(client, bench):
    body = client.get("/api/interlock", params={"workpiece": "W-NEW", "device_id": "D1"}).json()
    assert body["allowed"] is True


def test_interlock_without_device_uses_current_device(client, bench):
    push_result(client, "W-LOCK", "D2", test_item="绝缘", result="FAIL")
    body = client.get("/api/interlock", params={"workpiece": "W-LOCK"}).json()
    assert body["device_id"] == "D2"
    assert body["allowed"] is False
    assert "FAIL" in body["reason"]


def test_interlock_without_device_and_no_record_is_denied(client, bench):
    body = client.get("/api/interlock", params={"workpiece": "UNKNOWN"}).json()
    assert body["allowed"] is False
    assert "device_id" in body["reason"]


def test_variable_errors(client, bench):
    assert client.get("/api/variable/nope").status_code == 404
    response = client.post("/api/variable/nope", json={"value": 1, "device_id": "D1"})
    assert response.status_code == 404

    services.add_variable("counter", "int", 5)
    missing_device = client.post("/api/variable/counter", json={"value": 6})
    assert missing_device.status_code == 422

    bad_int = client.post(
        "/api/variable/counter", json={"value": "abc", "device_id": "D1"}
    )
    assert bad_int.status_code == 400

    updated = client.post(
        "/api/variable/counter", json={"value": 7, "device_id": "D1"}
    )
    assert updated.status_code == 200
    assert updated.json()["value"] == 7


def test_variable_typed_values(client, bench):
    services.add_variable("enabled", "bool", "yes")
    read = client.get("/api/variable/enabled").json()
    assert read["value"] is True
    services.set_variable("enabled", "0", "D1")
    assert client.get("/api/variable/enabled").json()["value"] is False


def test_conflicting_duplicate_report_returns_409(client, bench):
    push_result(client, "W-DUP", "D1", test_item="电压", result="PASS")
    response = client.post(
        "/api/test-result",
        json={
            "workpiece": "W-DUP",
            "device_id": "D1",
            "test_item": "电压",
            "result": "FAIL",
            "program_version": "v1",
            "program_sha256": SHA_A,
        },
    )
    assert response.status_code == 409
    assert "冲突" in response.json()["detail"]
    body = client.get(
        "/api/interlock", params={"workpiece": "W-DUP", "device_id": "D2"}
    ).json()
    assert body["allowed"] is True  # 原 PASS 记录未被冲突上报覆盖


def test_unlock_then_new_test_item_fail_relocks(client, bench):
    push_result(client, "W-RE", "D1", test_item="电压", result="FAIL")
    assert services.list_locked_workpieces()
    services.unlock_workpiece("W-RE", "测试员", "返修复测", True)
    allowed = client.get(
        "/api/interlock", params={"workpiece": "W-RE", "device_id": "D2"}
    ).json()
    assert allowed["allowed"] is True

    # 新的测试项上报 FAIL，会重新锁定
    push_result(client, "W-RE", "D1", test_item="电压复测", result="FAIL")
    denied = client.get(
        "/api/interlock", params={"workpiece": "W-RE", "device_id": "D2"}
    ).json()
    assert denied["allowed"] is False


def test_workpiece_product_isolation(client, bench):
    """同一工件的 PASS 不能跨产品被当作前道记录复用。"""
    bindings = list(bench["bindings"]) + [
        {
            "device_id": "D2",
            "product": "P2",
            "program_version": "v2",
            "download_url": "http://testserver/programs/D2_p2.bin",
            "sha256": SHA_B,
        },
        {
            "device_id": "D3",
            "product": "P2",
            "program_version": "v2",
            "download_url": "http://testserver/programs/D3_p2.bin",
            "sha256": SHA_B,
        },
    ]
    services.replace_bindings(bindings)
    services.report_program_status("D2", "P2", "v2", SHA_B, True)
    services.report_program_status("D3", "P2", "v2", SHA_B, True)

    push_result(client, "W-X", "D1")  # 工件属于 P1，D1 PASS

    # 工件已属于 P1：D2 以 P2 上报必须拒绝
    response = client.post(
        "/api/test-result",
        json={
            "workpiece": "W-X",
            "device_id": "D2",
            "product": "P2",
            "program_version": "v2",
            "program_sha256": SHA_B,
            "test_item": "P2项",
            "result": "PASS",
        },
    )
    assert response.status_code == 400
    assert "产品" in response.json()["detail"]

    # 即便库里存在 D2/P2 的 PASS，也不能满足 D3/P1 的前道检查
    now = db.utc_now_iso()
    with services._tx() as conn:  # noqa: SLF001 - 直接构造跨产品数据验证隔离
        conn.execute(
            """
            INSERT INTO test_results
                (workpiece, device_id, product, test_item, result,
                 tested_at, reported_at, trusted)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """,
            ("W-X", "D2", "P2", "P2项", "PASS", now, now),
        )
    body = client.get(
        "/api/interlock",
        params={"workpiece": "W-X", "device_id": "D3", "product": "P1"},
    ).json()
    assert body["allowed"] is False
    assert "D2" in body["reason"]

    # 用 P2 查询 P1 工件，直接按产品不一致拒绝
    mismatch = client.get(
        "/api/interlock",
        params={"workpiece": "W-X", "device_id": "D3", "product": "P2"},
    ).json()
    assert mismatch["allowed"] is False
    assert "产品" in mismatch["reason"]

    # 反向场景：先以 P2 建立工件，再以 P1 上报同样拒绝
    push_result(client, "W-Y", "D2", product="P2", test_item="P2项", program_version="v2", sha256=SHA_B)
    conflict = client.post(
        "/api/test-result",
        json={
            "workpiece": "W-Y",
            "device_id": "D1",
            "product": "P1",
            "program_version": "v1",
            "program_sha256": SHA_A,
            "test_item": "P1项",
            "result": "PASS",
        },
    )
    assert conflict.status_code == 400


def test_variable_prefix_filter(bench):
    services.add_variable("line_a", "str", "x")
    services.add_variable("line_b", "str", "y")
    services.add_variable("linex", "str", "z")
    services.add_variable("other", "int", 1)
    assert [item["name"] for item in services.list_variables("line_")] == [
        "line_a",
        "line_b",
    ]
    assert [item["name"] for item in services.list_variables("line_a")] == ["line_a"]
    assert services.list_variables("nothing") == []
    assert len(services.list_variables()) == 4


def test_variable_name_must_be_url_safe(bench):
    for bad_name in ("a/b", "a?b", "a b", "1abc", "中文"):
        with pytest.raises(services.ValidationError):
            services.add_variable(bad_name, "str", "x")
    created = services.add_variable("line_2.ready-x", "str", "ok")
    assert created["name"] == "line_2.ready-x"


def test_dashboard_uses_tested_at_not_report_time(client, bench):
    old_time = (db.utc_now().astimezone(config.timezone()) - timedelta(days=2)).isoformat()
    services.report_test_result(
        workpiece="OLD-WP",
        device_id="D1",
        test_item="电压",
        result="PASS",
        program_version="v1",
        program_sha256=SHA_A,
        tested_at=old_time,
    )
    push_result(client, "TODAY-WP", "D1")
    snapshot = services.dashboard_snapshot()
    assert snapshot["total"] == 1
    assert snapshot["pass"] == 1
    assert [item["workpiece"] for item in snapshot["latest"]] == ["TODAY-WP"]


def test_untrusted_fail_included_in_fail_distribution(client, bench):
    client.post(
        "/api/program/status",
        json={
            "device_id": "D2",
            "product": "P1",
            "program_version": "v0",
            "sha256": SHA_B,
            "sha256_ok": False,
        },
    )
    push_result(client, "UF-WP", "D2", test_item="绝缘", result="FAIL")
    snapshot = services.dashboard_snapshot()
    assert snapshot["fail"] == 1
    assert snapshot["trusted_total"] == 0
    assert snapshot["yield"] is None
    assert snapshot["fail_by_item"] == [{"label": "绝缘", "count": 1}]
    assert snapshot["fail_by_device"] == [{"label": "D2", "count": 1}]


def test_program_drift_detects_checksum_only_report(client, bench):
    client.post(
        "/api/program/status",
        json={
            "device_id": "D1",
            "product": "P1",
            "sha256": SHA_B,
            "sha256_ok": False,
        },
    )
    drifts = {item["device_id"]: item for item in services.program_drift()}
    assert "D1" in drifts
    assert "未上报程序版本" in drifts["D1"]["drift_reason"]
    assert "校验和不一致" in drifts["D1"]["drift_reason"]


def test_program_drift_detects_selfcheck_failure_without_versions(client, bench):
    response = client.post(
        "/api/program/status",
        json={"device_id": "D1", "product": "P1", "sha256_ok": False},
    )
    assert response.json()["trusted"] is False
    drifts = {item["device_id"]: item for item in services.program_drift()}
    assert "D1" in drifts
    assert "自检校验失败" in drifts["D1"]["drift_reason"]


def test_backfilled_old_result_does_not_override_newer_state(client, bench):
    start_iso, _ = db.today_bounds_utc()
    old_time = (db.parse_ts(start_iso) - timedelta(hours=2)).isoformat()
    newer = services.report_test_result(
        workpiece="W-BF",
        device_id="D1",
        test_item="电压",
        result="PASS",
        program_version="v1",
        program_sha256=SHA_A,
        tested_at=db.utc_now_iso(),
    )
    assert newer["stale"] is False
    assert newer["workpiece_status"]["status"] == "PASS"

    backfill = services.report_test_result(
        workpiece="W-BF",
        device_id="D1",
        test_item="电流",
        result="FAIL",
        program_version="v1",
        program_sha256=SHA_A,
        tested_at=old_time,
    )
    assert backfill["stale"] is True
    assert backfill["workpiece_status"]["status"] == "PASS"
    assert backfill["workpiece_status"]["locked"] is False
    assert services.list_locked_workpieces() == []

    allowed = client.get(
        "/api/interlock", params={"workpiece": "W-BF", "device_id": "D2"}
    ).json()
    assert allowed["allowed"] is True

    snapshot = services.dashboard_snapshot()
    assert snapshot["total"] == 1
    assert snapshot["fail"] == 0


def test_future_tested_at_is_clamped_and_does_not_block_later_fail(client, bench):
    future_time = (db.utc_now() + timedelta(days=365)).isoformat()
    first = services.report_test_result(
        workpiece="W-FUT",
        device_id="D1",
        test_item="电压",
        result="PASS",
        program_version="v1",
        program_sha256=SHA_A,
        tested_at=future_time,
    )
    assert first["tested_at_adjusted"] is True
    assert first["stale"] is False

    fail = client.post(
        "/api/test-result",
        json={
            "workpiece": "W-FUT",
            "device_id": "D2",
            "test_item": "绝缘",
            "result": "FAIL",
            "program_version": "v1",
            "program_sha256": SHA_A,
            "tested_at": db.utc_now_iso(),
        },
    )
    body = fail.json()
    assert body["stale"] is False
    assert body["workpiece_status"]["locked"] is True


def test_small_clock_skew_fail_still_locks(client, bench):
    now = db.utc_now()
    services.report_test_result(
        workpiece="W-SKEW",
        device_id="D1",
        test_item="电压",
        result="PASS",
        program_version="v1",
        program_sha256=SHA_A,
        tested_at=now.isoformat(),
    )
    fail = services.report_test_result(
        workpiece="W-SKEW",
        device_id="D2",
        test_item="绝缘",
        result="FAIL",
        program_version="v1",
        program_sha256=SHA_A,
        tested_at=(now - timedelta(seconds=60)).isoformat(),
    )
    assert fail["stale"] is False
    assert fail["workpiece_status"]["locked"] is True


def test_replace_bindings_validation(bench):
    with pytest.raises(services.ValidationError):
        services.replace_bindings(
            [
                {
                    "device_id": "D1",
                    "product": "P1",
                    "program_version": "v1",
                    "download_url": "http://x/y.bin",
                    "sha256": "not-a-sha",
                }
            ]
        )
    with pytest.raises(services.ValidationError):
        services.replace_bindings(
            [
                {
                    "device_id": "D1",
                    "product": "P1",
                    "program_version": "v1",
                    "download_url": "ftp://x/y.bin",
                    "sha256": SHA_A,
                }
            ]
        )
    with pytest.raises(services.ValidationError):
        services.replace_bindings(
            [
                {
                    "device_id": "D1",
                    "product": "P1",
                    "program_version": "v1",
                    "download_url": "http://x/y.bin",
                    "sha256": SHA_A,
                },
                {
                    "device_id": "D1",
                    "product": "P1",
                    "program_version": "v2",
                    "download_url": "http://x/z.bin",
                    "sha256": SHA_B,
                },
            ]
        )


def test_upstream_rule_validation(bench):
    with pytest.raises(services.ValidationError):
        services.replace_upstream_rules(
            [{"product": "", "device_id": "D1", "upstream_device_id": "D1"}]
        )


def test_unlock_unknown_workpiece(bench):
    with pytest.raises(services.NotFoundError):
        services.unlock_workpiece("NOPE", "op", "reason", True)


def test_dashboard_fail_distribution(client, bench):
    push_result(client, "W1", "D1", test_item="电压", result="FAIL")
    push_result(client, "W2", "D1", test_item="电压", result="PASS")
    push_result(client, "W3", "D1", test_item="电流", result="FAIL")
    snapshot = services.dashboard_snapshot()
    assert snapshot["fail"] == 2
    assert snapshot["fail_by_item"][0] == {"label": "电压", "count": 1} or snapshot[
        "fail_by_item"
    ][0] == {"label": "电流", "count": 1}
    assert {item["label"] for item in snapshot["fail_by_item"]} == {"电压", "电流"}
    assert snapshot["by_device"][0]["fail"] == 2
