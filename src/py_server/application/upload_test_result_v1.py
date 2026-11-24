"""用例：MES V1.3 整单测试结果上报。

入库分两张表：test_reports（整单主表）+ test_report_details（明细子表），
通过 report_id 关联；幂等键 request_id 在主表唯一。
"""

from __future__ import annotations

import time
from datetime import datetime

from .. import config, db, engine as eg
from ..constants import (
    BOARD_FINAL,
    BOARD_LOCK,
    BOARD_NORMAL,
    DETAIL_RESULT_FAIL,
    DETAIL_RESULT_PASS,
    FINAL_REPORT_FALSE,
    FINAL_REPORT_TRUE,
    NEXT_END,
    NEXT_LOCK,
    RESULT_FAIL,
    RESULT_PASS,
)
from ..repositories import product_flow_store, report_details_store, report_repo, report_route, station_repo
from ..repositories.base import with_conn


class UploadValidationError(Exception):
    """请求数据不合法（对应业务码 40001/40002）。"""


class UploadConflictError(Exception):
    """重复提交但内容冲突（对应业务码 409）。"""


def _parse_testexecutetime(text: str) -> datetime:
    """解析 yyyy/M/d HH:mm:ss.SSS；供将来按测试时间统计使用。"""
    for fmt in ("%Y/%m/%d %H:%M:%S.%f", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=config.timezone())
        except ValueError:
            continue
    raise UploadValidationError(f"testexecutetime 格式不合法：{text}")


def _duration_seconds(text: str) -> int:
    """解析 HH:mm:ss.SSS 为整秒。"""
    try:
        parts = text.split(":")
        h, m = int(parts[0]), int(parts[1])
        sec = float(parts[2])
        return max(0, int(h * 3600 + m * 60 + sec))
    except (ValueError, IndexError):
        return 0


def execute(
    *,
    payload: dict,
    headers: dict,
    report_one,
) -> dict:
    """整单入库（主子表）+ 汇总维护；同一 request_id 重复提交幂等。"""
    request_id = (headers.get("x-request-id") or "").strip()
    barcode = payload["barcode"].strip()
    station = payload["station"].strip()
    result = payload["result"].strip().upper()
    if result not in (RESULT_PASS, RESULT_FAIL):
        raise UploadValidationError(f"result 只能是 {RESULT_PASS} 或 {RESULT_FAIL}")
    is_final_report = str(
        payload.get("isfinalreport") or FINAL_REPORT_FALSE
    ).strip().lower()
    if is_final_report not in (FINAL_REPORT_TRUE, FINAL_REPORT_FALSE):
        raise UploadValidationError(
            f"isfinalreport 只能是 {FINAL_REPORT_TRUE} 或 {FINAL_REPORT_FALSE}"
        )
    details = payload["details"]
    if not details:
        raise UploadValidationError("details 不得为空")
    for d in details:
        if d["TestResult"] not in (DETAIL_RESULT_PASS, DETAIL_RESULT_FAIL):
            raise UploadValidationError(f"明细 TestResult 不合法：{d['TestResult']}")

    # 幂等：主表按 request_id 查
    with with_conn() as conn:
        existing = report_repo.get_by_request_id(conn, request_id)
    if existing is not None:
        return {
            "success": True,
            "workpiece": existing["barcode"],
            "station": existing["station"],
            "result": existing["result"],
            "retest": False,
            "request_id": request_id,
            "duplicate": True,
        }

    device_id = station
    duration = _duration_seconds(payload["testlongtime"])
    now_ts = int(time.time())
    step_info = report_route.step_for_station(station)
    step_no = str(step_info["step_no"]) if step_info else ""
    report_engine = eg.get_details_engine()

    # 复测判定：同一条码主表已有记录即为复测
    with with_conn() as conn:
        from sqlalchemy import func, select

        from ..engine import test_reports

        exists_retest = conn.execute(
            select(func.count()).select_from(test_reports).where(test_reports.c.barcode == barcode)
        ).fetchone()[0] > 0
        is_retest = exists_retest

    # 每条明细作为一条内部结果上报（保留原有可信性/联锁链路）
    for detail in details:
        report_one(
            workpiece=barcode,
            device_id=device_id,
            test_item=detail["TestStep"],
            result=RESULT_PASS if detail["TestResult"] == DETAIL_RESULT_PASS else RESULT_FAIL,
            measured_value=detail["MeasureValue"],
            program_version=payload["programversion"],
            program_sha256=None,
            product=None,
            tested_at=None,
        )

    # 写主子表
    report = {
        "request_id": request_id,
        "station": station,
        "componentcode": payload["componentcode"],
        "barcode": barcode,
        "programname": payload["programname"],
        "programversion": payload["programversion"],
        "testexecutetime": payload["testexecutetime"],
        "result": result,
        "testlongtime": payload["testlongtime"],
        "isfinalreport": is_final_report,
        "created_at": db.utc_now_iso(),
    }
    detail_rows = [
        {
            "TestItem": d["TestItem"],
            "TestStep": d["TestStep"],
            "StandardValue": d["StandardValue"],
            "UpperValue": d["UpperValue"],
            "LowerValue": d["LowerValue"],
            "MeasureValue": d["MeasureValue"],
            "TestResult": d["TestResult"],
            "TestBeginTime": d["TestBeginTime"],
            "TestEndTime": d["TestEndTime"],
        }
        for d in details
    ]
    detail_table = ""
    with with_conn() as conn:
        detail_table = report_repo.insert_report(
            conn, report=report, details=detail_rows, step_no=step_no, report_engine=report_engine
        )
    # 总览表（details.db）：failed_step = 失败项 TestStep（成功为空）
    failed_steps = [d["TestStep"] for d in details if d["TestResult"] == DETAIL_RESULT_FAIL]
    overview_report = dict(report)
    overview_report["traycode"] = str(payload.get("traycode") or "")
    report_details_store.insert_overview(
        overview_report,
        ",".join(failed_steps),
        step_no=step_no,
        details_table=detail_table,
        engine=report_engine,
    )

    # 写产品流转库（当前状态 + 流转记录）
    if step_info:
        current_step = str(step_info["step_no"])
        step_value = str(step_info["step_no"])
        if result == RESULT_FAIL:
            next_step = NEXT_LOCK
        elif is_final_report == FINAL_REPORT_TRUE:
            next_step = NEXT_END
        else:
            next_step = str(int(step_value) + 1) if step_value.isdigit() else ""
        board_status = (
            BOARD_LOCK
            if result == RESULT_FAIL
            else BOARD_FINAL
            if is_final_report == FINAL_REPORT_TRUE
            else BOARD_NORMAL
        )
        product_flow_store.upsert_flow(
            barcode=barcode,
            componentcode=payload["componentcode"],
            traycode=str(payload.get("traycode") or ""),
            board_status=board_status,
            step_no=current_step,
            next_step=next_step,
            device=station,
            note="test pass" if result == RESULT_PASS else "test fail",
            changed_at=db.utc_now_iso(),
        )

    # 维护看板汇总
    failed_items = [d["TestItem"] for d in details if d["TestResult"] == DETAIL_RESULT_FAIL]
    with with_conn() as conn:
        station_repo.apply_result(
            conn,
            device_id=device_id,
            name=station,
            barcode=barcode,
            result=result,
            is_retest=is_retest,
            duration_seconds=duration,
            status_since=now_ts,
            failed_items=failed_items,
        )

    return {
        "success": True,
        "workpiece": barcode,
        "station": station,
        "result": result,
        "retest": is_retest,
        "request_id": request_id,
    }
