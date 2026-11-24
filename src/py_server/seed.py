"""演示数据初始化脚本。

用法::

    python -m py_server.seed            # 空库初始化演示配置
    python -m py_server.seed --reset    # 清空后重建（仅用于本工具自己的数据库）
    python -m py_server.seed --demo     # 额外生成今天的测试数据，便于查看板

注意：--reset 会删除本系统全部业务数据，请勿对生产库执行。
"""

from __future__ import annotations

import argparse
import hashlib
import random
import sys
from pathlib import Path
from urllib.parse import quote

from . import config, db, master_seed, services
from .repositories import dashboard_repo
from .repositories.base import with_conn
from . import engine

VARIABLES = [
    ("line_mode", "str", "AUTO"),
    ("target_qty", "int", 1200),
    ("alarm_enabled", "bool", True),
    ("last_result", "str", ""),
]

# 设备、产品、程序版本、说明
PROGRAMS = [
    ("TEST-01", "P-1001", "v1.2.0"),
    ("TEST-02", "P-1001", "v1.2.0"),
    ("TEST-03", "P-1001", "v1.2.0"),
    ("AOI-01", "P-1001", "v2.0.1"),
    ("TEST-04", "P-1002", "v3.0.0"),
]

# 设备 -> 前道关键设备；产品留空表示对所有产品生效
UPSTREAM = [
    ("", "TEST-02", "TEST-01"),
    ("", "TEST-03", "TEST-02"),
    ("", "AOI-01", "TEST-03"),
]

# 设备上报的程序状态：前三个与绑定一致；TEST-03 故意制造漂移；AOI-01 未上报
REPORTED = {
    "TEST-01": ("v1.2.0", True),
    "TEST-02": ("v1.2.0", True),
    "TEST-03": ("v1.1.0", False),
}


def _clear_all() -> None:
    """演示脚本清库：通过 repository 的 delete 语句完成，不直接写 SQL。"""
    from sqlalchemy import delete

    from . import engine
    from .repositories.base import with_conn

    with with_conn() as conn:
        for table in (
            engine.program_bindings,
            engine.program_pull_logs,
            engine.program_status_logs,
            engine.workpieces,
            engine.unlock_logs,
            engine.test_results,
            engine.variables,
            engine.upstream_devices,
            engine.settings,
        ):
            conn.execute(delete(table))


def _write_program_file(device: str, product: str, version: str) -> tuple[str, str]:
    """写一个占位程序文件，返回 (URL, SHA256)。"""
    filename = f"fw_{device}_{product}_{version}.bin".replace(" ", "_")
    content = (
        f"DEMO PROGRAM\ndevice={device}\nproduct={product}\nversion={version}\n"
        + ("0123456789abcdef" * 64)
    ).encode()
    target = config.program_dir() / filename
    target.write_bytes(content)
    sha256 = hashlib.sha256(content).hexdigest()
    url = f"{config.api_public_base()}/programs/{quote(filename)}"
    return url, sha256





def seed_test_reports() -> None:
    """演示数据：10 个产品各走 S1/S2/S3 三道工序，每份报告 10 条明细。"""
    import copy
    import json
    from datetime import datetime, timezone, timedelta

    from . import config
    from sqlalchemy import text
    from .repositories import product_flow_store, report_repo, report_route
    from .repositories.base import with_conn

    template_path = config.PROJECT_ROOT / "docs" / "MesFormat" / "mesUploadTestDataFormat.json"
    try:
        template = json.loads(template_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        template = {
            "station": "39C0-L2-1F-DIP16-FCT01",
            "componentcode": "L120201091", "barcode": "SN202611170001",
            "programname": "TEST-DUT-001", "programversion": "V0.0.2",
            "testexecutetime": "2025/4/22 13:55:35.123",
            "isfinalreport": "false", "result": "FAIL", "testlongtime": "00:00:06.300",
            "details": [{
                "TestItem": "测试温度", "TestStep": "SOC_HW_ID1", "StandardValue": "1.10",
                "UpperValue": "1.20", "LowerValue": "0.90", "MeasureValue": "1.12",
                "TestResult": "true", "TestBeginTime": "13:55:35.123", "TestEndTime": "13:55:37.123",
            }],
        }

    # 每道工序对应测试设备
    STEP_STATIONS = [("1", "TEST-01"), ("2", "TEST-02"), ("3", "TEST-03")]
    # 测试条目模板：10 个
    TEST_ITEMS = [
        "上电电压", "工作电流", "测试温度", "绝缘阻抗", "通信握手",
        "固件版本", "功能自检", "耐压测试", "信号强度", "外观检查",
    ]

    base_time = datetime(2026, 11, 18, 9, 0, 0, tzinfo=timezone.utc)
    reports: list[tuple[dict, list[dict]]] = []
    seq = 0
    for i in range(1, 11):  # 10 个产品
        barcode = f"SN20261118{i:04d}"
        componentcode = f"L1202010{(90 + i):02d}"
        traycode = f"T{2000 + i:05d}"  # 演示托盘码
        for step_index, (step_code, station) in enumerate(STEP_STATIONS, start=1):
            seq += 1
            data = copy.deepcopy(template)
            data["barcode"] = barcode
            data["componentcode"] = componentcode
            data["traycode"] = traycode
            data["station"] = station
            data["programname"] = f"TEST-DUT-S{step_code}"
            data["programversion"] = f"V0.0.{i}"
            t = base_time + timedelta(minutes=seq * 3, seconds=i)
            data["testexecutetime"] = t.strftime("%Y/%m/%d %H:%M:%S.") + f"{t.microsecond // 1000:03d}"
            data["testlongtime"] = f"00:00:{5 + i:02d}.{100 + i:03d}"
            # 10 条明细
            details = []
            for j, item_name in enumerate(TEST_ITEMS):
                d = copy.deepcopy(template["details"][0])
                d["TestItem"] = item_name
                d["TestStep"] = f"S{step_code}_{j + 1:02d}"
                d["StandardValue"] = f"{1.00 + j * 0.05:.2f}"
                d["UpperValue"] = f"{1.20 + j * 0.05:.2f}"
                d["LowerValue"] = f"{0.80 + j * 0.05:.2f}"
                measure = 1.05 + (i * 0.002) + (j * 0.01) + (step_index * 0.01)
                d["MeasureValue"] = f"{measure:.2f}"
                # 每份报告控制 1~2 条失败，其他通过
                fail_indexes = {(i + step_index) % 10, (i + step_index + 3) % 10}
                d["TestResult"] = "false" if j in fail_indexes else "true"
                d["TestBeginTime"] = (t + timedelta(seconds=j)).strftime("%H:%M:%S.") + f"{t.microsecond // 1000:03d}"
                d["TestEndTime"] = (t + timedelta(seconds=j + 1)).strftime("%H:%M:%S.") + f"{t.microsecond // 1000:03d}"
                details.append(d)
            data["details"] = details
            data["result"] = "FAIL" if any(d["TestResult"] == "false" for d in details) else "PASS"
            data["isfinalreport"] = "true" if step_code == "3" else "false"

            report = {k: data[k] for k in (
                "station", "componentcode", "traycode", "barcode",
                "programname", "programversion", "testexecutetime",
                "result", "testlongtime", "isfinalreport"
            )}
            report["step_no"] = step_code
            report["request_id"] = f"demo{seq:032d}"
            report["created_at"] = t.astimezone(timezone.utc).isoformat(timespec="seconds")
            reports.append((report, details))

    with with_conn() as conn:
        from sqlalchemy import delete

        from .engine import test_reports, workpieces
        from .repositories import report_details_store, workpiece_repo

        report_details_store.drop_all_tables()
        product_flow_store.reset_all()
        conn.execute(delete(test_reports))
        for report, details in reports:
            step_info = report_route.step_for_station(report["station"], conn)
            main_report = {k: v for k, v in report.items() if k != "traycode"}
            main_report.pop("step_no", None)
            detail_table = report_repo.insert_report(
                conn, report=main_report, details=details, step_no=report["step_no"]
            )
            failed_steps = [d["TestStep"] for d in details if d["TestResult"] == "false"]
            overview_report = dict(report)
            report_details_store.insert_overview(
                overview_report,
                ",".join(failed_steps),
                step_no=report["step_no"],
                details_table=detail_table,
            )
            # 产品流转库：每个产品三次流转
            if step_info:
                product_flow_store.upsert_flow(
                    barcode=report["barcode"], componentcode=report["componentcode"],
                    traycode=traycode,
                    board_status=("normal" if report["result"] == "PASS" else "lock")
                        if report["isfinalreport"] == "true" else "normal",
                    step_no=str(step_info["step_no"]),
                    next_step=str(step_index + 1) if step_index < len(STEP_STATIONS) else "END",
                    device=report["station"],
                    note=("test pass" if report["result"] == "PASS" else "test fail"),
                    changed_at=report["created_at"],
                )
            # 同步工件主表
            workpiece_repo.insert_workpiece_ignore(
                conn, workpiece=report["barcode"], product="P-1001", now=report["created_at"]
            )
            conn.execute(
                workpieces.update()
                .where(workpieces.c.workpiece == report["barcode"])
                .values(
                    product="P-1001",
                    current_device=report["station"],
                    status="FAIL" if report["result"] == "FAIL" else "PASS",
                    updated_at=report["created_at"],
                )
            )


def seed_station_summary() -> None:
    """演示数据：监控看板用的 station_summary 汇总表。"""
    import time
    now_ts = int(time.time())
    # (name, status, barcode, total, first_pass, retest, fail, 时长秒)
    # 通过/失败: 时长=测试用时; 其他: 时长=已在此状态持续时间
    now_name = {
        "TEST-01": ("上电测试机", "测试中", "SN202611170001", 128, 118, 6, 4, 35),
        "TEST-01B": ("上电测试机B", "通过", "SN202611170002", 256, 240, 10, 6, 42),
        "TEST-02": ("功能测试机", "空闲", "无条码", 95, 90, 3, 2, 180),
        "TEST-03": ("终检机", "失败", "SN202611170004", 40, 34, 2, 4, 58),
        "TEST-03B": ("终检机B", "通过", "SN202611170005", 77, 70, 4, 3, 30),
        "TEST-02B": ("功能测试机B", "测试中", "SN202611170006", 60, 55, 3, 2, 20),
    }
    with with_conn() as conn:
        conn.execute(engine.station_summary.delete())
        for device_id, (name, status, barcode, total, first_pass, retest, fail, seconds) in now_name.items():
            conn.execute(engine.station_summary.insert().values(
                device_id=device_id, name=name, status=status, barcode=barcode,
                total=total, first_pass=first_pass, retest_pass=retest, fail=fail,
                status_since=now_ts - seconds, test_duration=seconds,
            ))
        # 失败项明细演示数据（后端维护，前端只读）
        conn.execute(engine.station_fail_detail.delete())
        fail_rows = [
            ("TEST-01", "上电电流超限", "SN202611169901"),
            ("TEST-01", "绝缘阻抗低", "SN202611169902"),
            ("TEST-02", "功能项F3失败", "SN202611169903"),
            ("TEST-02", "通信超时", "SN202611169904"),
            ("TEST-03", "耐压测试失败", "SN202611170004"),
            ("TEST-03", "包装标签缺失", "SN202611170041"),
            ("TEST-03", "外观划痕", "SN202611170042"),
        ]
        for dev, item, bc in fail_rows:
            conn.execute(engine.station_fail_detail.insert().values(
                device_id=dev, test_item=item, barcode=bc,
                failed_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(timespec="seconds"),
            ))

def seed(reset: bool = False, with_demo: bool = False) -> None:
    """执行 seed。"""
    db.init_db()
    existing = 0
    existing = dashboard_repo.business_data_count()
    if existing and not reset:
        print(
            f"数据库已有 {existing} 条程序绑定，未做修改。\n"
            "如需重建演示数据请加 --reset（会清空本系统全部数据）。",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if reset:
        _clear_all()

    # 程序绑定 + 占位程序文件
    bindings: dict[tuple[str, str], dict] = {}
    for device, product, version in PROGRAMS:
        url, sha = _write_program_file(device, product, version)
        bindings[(device, product)] = {
            "device_id": device,
            "product": product,
            "program_version": version,
            "download_url": url,
            "sha256": sha,
        }
    services.replace_bindings(bindings.values())

    # 设备上报状态（部分一致、部分漂移、部分未上报）
    for device, product, version in PROGRAMS:
        info = REPORTED.get(device)
        if info is None:
            continue
        reported_version, sha_ok = info
        binding = bindings[(device, product)]
        services.report_program_status(
            device_id=device,
            product=product,
            reported_version=reported_version,
            reported_sha256=binding["sha256"] if sha_ok else "0" * 64,
            sha256_ok=sha_ok,
        )

    # 开放性变量
    for name, type_name, value in VARIABLES:
        services.add_variable(name, type_name, value)

    # 前道关键设备配置
    services.replace_upstream_rules(
        [
            {"product": product, "device_id": device, "upstream_device_id": upstream}
            for product, device, upstream in UPSTREAM
        ]
    )

    # 主数据（app_pages 页面）：工序/设备/程序/产品
    master_seed.seed_master_data()
    seed_station_summary()
    seed_test_reports()

    if with_demo:
        _seed_demo_runs()

    print("演示数据初始化完成。")
    print("  程序绑定：", ", ".join(f"{d}/{p}" for d, p, _ in PROGRAMS))
    print("  前道规则：", ", ".join(f"{d}<-{u}" for _, d, u in UPSTREAM))
    print("  开放变量：", ", ".join(name for name, _, _ in VARIABLES))
    print(f"  接口服务： {config.api_public_base()}")
    print("  启动页面： uv run streamlit run src/py_server/streamlit_app.py")


def _seed_demo_runs() -> None:
    """按前道顺序上报一批今天的测试数据；包含 FAIL 与不可信数据。"""
    rng = random.Random(20261112)
    # 先让主力设备上报可信程序状态，保证正常测试结果能推进工件状态（PASS/FAIL）
    # 直接读取已写入的 program_bindings，避免重新生成文件
    from .repositories import binding_repo
    from .repositories.base import with_read_conn

    sha_map = {}
    with with_read_conn() as conn:
        for device in ("TEST-01", "TEST-02", "TEST-03"):
            binding = binding_repo.try_binding(conn, device, "P-1001")
            if binding:
                sha_map[device] = binding["sha256"]
                if device in ("TEST-01", "TEST-02"):
                    services.report_program_status(
                        device_id=device,
                        product="P-1001",
                        reported_version=binding["program_version"],
                        reported_sha256=binding["sha256"],
                        sha256_ok=True,
                    )
    for index in range(1, 25):
        workpiece = f"WP-{index:04d}"
        # 前道 TEST-01：大部分 PASS，少量 FAIL
        first = "FAIL" if index % 11 == 0 else "PASS"
        services.report_test_result(
            workpiece=workpiece,
            device_id="TEST-01",
            test_item="上电电流",
            result=first,
            measured_value=f"{rng.uniform(0.8, 1.3):.3f}A",
            program_version="v1.2.0",
            program_sha256=sha_map.get("TEST-01"),
        )
        if first == "FAIL":
            continue
        # 第二道 TEST-02：少量 FAIL
        second = "FAIL" if index % 7 == 0 else "PASS"
        services.report_test_result(
            workpiece=workpiece,
            device_id="TEST-02",
            test_item="绝缘电阻",
            result=second,
            measured_value=f"{rng.uniform(80, 120):.1f}MΩ",
            program_version="v1.2.0",
            program_sha256=sha_map.get("TEST-02"),
        )
        if second == "FAIL":
            continue
        # TEST-03 当前版本漂移：它上报的数据不可信，演示看板“不可信排除”
        if index % 5 == 0:
            services.report_test_result(
                workpiece=workpiece,
                device_id="TEST-03",
                test_item="耐压",
                result="PASS",
                measured_value=f"{rng.uniform(1.4, 1.6):.2f}kV",
                program_version="v1.1.0",
                program_sha256="0" * 64,
            )
    # 一个已锁定的工件，供“工序锁”页面演示人工解锁
    services.report_test_result(
        workpiece="WP-LOCKED",
        device_id="TEST-01",
        test_item="上电电流",
        result="PASS",
        measured_value="1.021A",
        program_version="v1.2.0",
        program_sha256=sha_map.get("TEST-01"),
    )
    services.report_test_result(
        workpiece="WP-LOCKED",
        device_id="TEST-02",
        test_item="绝缘电阻",
        result="FAIL",
        measured_value="12.0MΩ",
        program_version="v1.2.0",
    )


def main() -> None:
    """执行 main。"""
    parser = argparse.ArgumentParser(description="初始化旁路 MES 演示数据")
    parser.add_argument("--reset", action="store_true", help="清空本系统全部业务数据后重建")
    parser.add_argument("--demo", action="store_true", help="生成今天的演示测试数据")
    args = parser.parse_args()
    seed(reset=args.reset, with_demo=args.demo)


if __name__ == "__main__":
    main()
