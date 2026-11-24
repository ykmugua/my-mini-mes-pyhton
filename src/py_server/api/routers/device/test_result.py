"""测试结果上报路由：仅保留 V1.3 整单上传主接口。"""

from __future__ import annotations

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from .... import services
from ....application.upload_test_result_v1 import (
    UploadConflictError,
    UploadValidationError,
    execute as upload_execute,
)
from ...schemas_v1 import TestResultUploadIn

router = APIRouter(tags=["test_result"])


def _envelope(success: bool, message: str, code: int, result=None) -> dict:
    """执行 envelope。"""
    return {"success": success, "message": message, "code": code, "result": result}


# ---------------------------------------------------------------------------
# V1.3：整单测试结果上传（机台主接口）
# ---------------------------------------------------------------------------
@router.post("/api/v1/test-results")
async def post_test_results_v1(
    payload: TestResultUploadIn,
    x_device_sn: str = Header(default="", alias="x-device-sn"),
    x_timestamp: str = Header(default="", alias="x-timestamp"),
    x_request_id: str = Header(default="", alias="x-request-id"),
):
    """整单测试结果上报；按协议返回 {success,message,code,result} 信封。"""
    if not x_device_sn or not x_timestamp or not x_request_id:
        return JSONResponse(status_code=200, content=_envelope(False, "缺少必填请求头", 40001))
    if x_device_sn != payload.station:
        return JSONResponse(status_code=200, content=_envelope(False, "设备 SN 与 station 不一致", 40003))

    headers = {
        "x-device-sn": x_device_sn,
        "x-timestamp": x_timestamp,
        "x-request-id": x_request_id,
    }
    try:
        data = upload_execute(
            payload=payload.model_dump(),
            headers=headers,
            report_one=services.report_test_result,
        )
    except UploadValidationError as exc:
        return JSONResponse(status_code=200, content=_envelope(False, str(exc), 40001))
    except UploadConflictError as exc:
        return JSONResponse(status_code=200, content=_envelope(False, str(exc), 409))
    except Exception as exc:
        return JSONResponse(status_code=200, content=_envelope(False, f"服务端内部错误：{exc}", 50000))

    return _envelope(True, "success", 0, data)
