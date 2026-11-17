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



def seed_station_summary() -> None:
    """演示数据：产线监控看板用的 station_summary 汇总表。"""
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

    # 主数据（app_pages 页面）：工序/线体/设备/程序/产品
    master_seed.seed_master_data()
    seed_station_summary()

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
            )
    # 一个已锁定的工件，供“工序锁”页面演示人工解锁
    services.report_test_result(
        workpiece="WP-LOCKED",
        device_id="TEST-01",
        test_item="上电电流",
        result="PASS",
        measured_value="1.021A",
        program_version="v1.2.0",
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
    parser = argparse.ArgumentParser(description="初始化旁路 MES 演示数据")
    parser.add_argument("--reset", action="store_true", help="清空本系统全部业务数据后重建")
    parser.add_argument("--demo", action="store_true", help="生成今天的演示测试数据")
    args = parser.parse_args()
    seed(reset=args.reset, with_demo=args.demo)


if __name__ == "__main__":
    main()
