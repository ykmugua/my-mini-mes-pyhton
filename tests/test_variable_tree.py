"""三层变量树：拆分与组装（向后兼容扁平变量）。"""

from py_server import services


def test_split_variable_name():
    assert services.split_variable_name("line_mode") == ("line_mode", "", "")
    assert services.split_variable_name("a.b") == ("a", "b", "")
    assert services.split_variable_name("a.b.c") == ("a", "b", "c")
    assert services.split_variable_name("a.b.c.d") == ("a", "b", "c.d")


def test_variables_tree_nested():
    variables = [
        {"name": "line1.status.ready", "value": True},
        {"name": "line1.status.mode", "value": "AUTO"},
        {"name": "zone2.device.temp", "value": 25},
    ]
    assert services.variables_tree(variables) == {
        "line1": {"status": {"ready": True, "mode": "AUTO"}},
        "zone2": {"device": {"temp": 25}},
    }


def test_variables_tree_keeps_flat_and_two_level():
    variables = [
        {"name": "line_mode", "value": "AUTO"},
        {"name": "a.b", "value": 1},
        {"name": "x.y.z", "value": "v"},
    ]
    tree = services.variables_tree(variables)
    assert tree["line_mode"] == "AUTO"
    assert tree["a"] == {"b": 1}
    assert tree["x"] == {"y": {"z": "v"}}


def test_tree_api_roundtrip(client):
    from tests.helpers import SHA_A

    services.add_variable("grp.sub.key", "int", "7")
    services.add_variable("standalone", "str", "v")
    body = client.get("/api/ui/variables/tree").json()
    assert body == {"grp": {"sub": {"key": 7}}, "standalone": "v"}
    # 设备仍可用完整路径读写
    got = client.get("/api/variable/grp.sub.key").json()
    assert got["value"] == 7


def test_variable_crud_api(client):
    assert client.post("/api/ui/variables", json={"name": "grp.sub.key", "type": "int", "value": "1"}).status_code == 200
    assert client.put("/api/ui/variables/grp.sub.key", json={"name": "g2.s2.k2"}).json()["name"] == "g2.s2.k2"
    assert client.patch("/api/ui/variables/g2.s2.k2", json={"type": "str", "value": "hello"}).json()["value"] == "hello"
    assert client.get("/api/ui/variables/tree").json() == {"g2": {"s2": {"k2": "hello"}}}
    assert client.delete("/api/ui/variables/g2.s2.k2").json()["deleted"] is True
    assert client.get("/api/ui/variables").json() == []


def test_variable_delete_missing_returns_404(client):
    assert client.delete("/api/ui/variables/nope").status_code == 404


def test_variable_rename_conflict(client):
    client.post("/api/ui/variables", json={"name": "a.b.c", "type": "str", "value": "1"})
    client.post("/api/ui/variables", json={"name": "x.y.z", "type": "str", "value": "2"})
    assert client.put("/api/ui/variables/a.b.c", json={"name": "x.y.z"}).status_code == 409



def test_float_variable(client):
    created = client.post("/api/ui/variables", json={"name": "sensor.temp.value", "type": "float", "value": "25.5"})
    assert created.status_code == 200, created.text
    assert created.json()["value"] == 25.5
    assert client.get("/api/variable/sensor.temp.value").json()["value"] == 25.5
    assert client.get("/api/ui/variables/tree").json()["sensor"]["temp"]["value"] == 25.5
    bad = client.post("/api/ui/variables", json={"name": "bad.f", "type": "float", "value": "abc"})
    assert bad.status_code == 400



def test_program_history_newest_first_and_delete(client):
    from py_server.repositories.base import with_conn
    from py_server.repositories import master_data_repo as m
    with with_conn() as conn:
        m.replace_programs(conn, [
            {"program_id": 1, "program_name": "HIST", "program_version": "v1", "version_description": "old", "sha256": "a", "download_url": "u1", "step_no": 1},
            {"program_id": 2, "program_name": "HIST", "program_version": "v3", "version_description": "new", "sha256": "b", "download_url": "u2", "step_no": 1},
        ])
    h = client.get("/api/ui/program-history", params={"name": "HIST"}).json()
    assert [x["program_version"] for x in h] == ["v3", "v1"]
    assert client.delete("/api/ui/program-version/1").status_code == 200
    assert [x["program_version"] for x in client.get("/api/ui/program-history", params={"name": "HIST"}).json()] == ["v3"]



def test_variable_device_read_write_logs(client):
    client.post("/api/ui/variables", json={"name": "log.test.value", "type": "int", "value": "5"})
    # device write (with device_id in body)
    r = client.post("/api/variable/log.test.value", json={"value": "9", "device_id": "D-LOG"})
    assert r.status_code == 200
    # device read (with device_id query)
    r = client.get("/api/variable/log.test.value", params={"device_id": "D-LOG"})
    assert r.json()["value"] == 9
    writes = client.get("/api/ui/variable-logs/write").json()
    reads = client.get("/api/ui/variable-logs/read").json()
    assert any(x["name"] == "log.test.value" and x["device_id"] == "D-LOG" for x in writes)
    assert any(x["name"] == "log.test.value" and x["device_id"] == "D-LOG" for x in reads)
