"""测试报告查询的只读聚合入口。

路由只负责参数校验与响应形状；跨多个 db_<step>.db / TestReport.db 的扫描、
筛选与明细定位统一放在 repository 层。
"""

from __future__ import annotations

import re
from typing import Any, Iterator

from sqlalchemy import text

from .. import config, engine as eg
from ..constants import ALL_OPTION, BOARD_LOCK, BOARD_NORMAL, RESULT_FAIL, RESULT_PASS, TRUE_TEXT
from . import master_data_repo, report_details_store
from .base import with_read_conn

_STEP_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")
_TABLE_RE = re.compile(r"SN_[0-9A-Za-z_]{1,40}_[0-9a-f]{16}")


def report_engines() -> Iterator[tuple[str, Any]]:
    """统一报告库只有一个；保留 tuple 形状以兼容现有调用。"""
    yield "", eg.get_details_engine()


def step_exists(step_no: str) -> bool:
    """执行 step_exists。"""
    if not _STEP_NAME_RE.fullmatch(step_no or ""):
        return False
    with with_read_conn() as conn:
        row = conn.execute(
            text("SELECT step_name FROM steps WHERE step_no = :sn"), {"sn": step_no}
        ).fetchone()
    return row is not None


def list_report_index(barcode: str | None = None, step_no: str | None = None) -> list[dict]:
    """列出report_index。"""
    rows: list[dict] = report_details_store.list_overview(barcode, step_no=step_no)
    rows.sort(key=lambda row: row.get("id", 0), reverse=True)
    return rows


def list_details(table: str, step_no: str | None = None) -> list[dict]:
    """按总览表名读明细；非法表名直接返回空列表。"""
    if not _TABLE_RE.fullmatch(table or ""):
        return []
    return report_details_store.list_details_by_table(table)


def latest_traycodes() -> list[dict]:
    """按条码返回最后一次测试上报的托盘码（产品查询展示用）。"""
    rows: list[dict] = report_details_store.list_overview(None)
    latest: dict[str, tuple[str, str, int]] = {}
    for row in rows:
        barcode = str(row.get("barcode") or "")
        if not barcode:
            continue
        key = (
            str(row.get("testexecutetime") or ""),
            str(row.get("traycode") or ""),
            int(row.get("id") or 0),
        )
        if barcode not in latest or key > latest[barcode]:
            latest[barcode] = key
    return [
        {"barcode": barcode, "traycode": value[1]}
        for barcode, value in sorted(latest.items())
    ]


def filter_options() -> dict:
    """测试报告筛选选项：产品/条码/托盘/设备来自工序报告库。"""
    products: set[str] = set()
    barcodes: set[str] = set()
    traycodes: set[str] = set()
    fixturecodes: set[str] = set()
    stations: set[str] = set()
    step_values: set[str] = set()
    for row in report_details_store.list_overview(None):
        step_value = str(row.get("step_no") or "").strip()
        if step_value:
            step_values.add(step_value)
        for target, key in (
            (products, "componentcode"),
            (barcodes, "barcode"),
            (traycodes, "traycode"),
            (fixturecodes, "fixturecode"),
            (stations, "station"),
        ):
            value = str(row.get(key) or "").strip()
            if value:
                target.add(value)

    step_names = {
        str(row.get("step_no") or ""): str(row.get("step_name") or "")
        for row in master_data_repo.list_steps()
    }
    default_path = config.details_db_path()
    steps = [
        {
            "step_no": step_no,
            "step_name": step_names.get(step_no, ""),
            "db_name": default_path.name,
        }
        for step_no in sorted(set(step_names) | step_values)
        if step_no
    ]
    if default_path.exists():
        steps.insert(
            0,
            {
                "step_no": "",
                "step_name": f"默认库（{default_path.name}）",
                "db_name": default_path.name,
            },
        )
    return {
        "products": sorted(products),
        "barcodes": sorted(barcodes),
        "traycodes": sorted(traycodes),
        "fixturecodes": sorted(fixturecodes),
        "stations": sorted(stations),
        "steps": steps,
    }


def query_reports(
    *,
    product: str | None = None,
    step_no: str | None = None,
    barcode: str | None = None,
    traycode: str | None = None,
    fixturecode: str | None = None,
    result: str | None = None,
    board_status: str | None = None,
    current_step: str | None = None,
    last_report_device: str | None = None,
    limit: int = 200,
) -> list[dict]:
    """查询reports。"""
    if step_no and not _STEP_NAME_RE.fullmatch(step_no):
        return []
    filtered: list[dict] = []
    for row in report_details_store.list_overview(barcode, step_no=step_no):
        if product and str(row.get("componentcode") or "") != product:
            continue
        if traycode and str(row.get("traycode") or "") != traycode:
            continue
        if fixturecode and str(row.get("fixturecode") or "/") != fixturecode:
            continue
        if result and str(row.get("result") or "") != result:
            continue
        if last_report_device and str(row.get("station") or "") != last_report_device:
            continue
        item = dict(row)
        report_step = str(item.get("step_no") or "").strip()
        item["step_no"] = report_step or (step_no or "")
        item["source_db"] = config.details_db_path().name
        if current_step and str(item["step_no"]) != str(current_step):
            continue
        if step_no and report_step and report_step != str(step_no):
            continue
        if board_status:
            report_result = str(item.get("result") or "")
            is_final = str(item.get("isfinalreport") or "").lower() == TRUE_TEXT
            if board_status == BOARD_NORMAL and (report_result != RESULT_PASS or is_final):
                continue
            if board_status == BOARD_LOCK and report_result != RESULT_FAIL:
                continue
            if board_status == "final" and not is_final:
                continue
        filtered.append(item)
    filtered.sort(
        key=lambda row: (
            str(row.get("testexecutetime") or ""),
            int(row.get("id") or 0),
        ),
        reverse=True,
    )
    return filtered[:limit]
