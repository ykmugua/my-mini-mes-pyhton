"""测试结果上报路由：仅保留 V1.3 整单上传主接口。"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .... import services
from ....application.upload_test_result_v1 import (
    UploadConflictError,
    UploadValidationError,
    execute as upload_execute,
)
from ...schemas_v1 import TestResultUploadIn

router = APIRouter(tags=["test_result"])


def _envelope(success: bool, message: str, code: str) -> dict:
    """返回设备端统一简化信封。"""
    return {"success": success, "code": code, "message": message, "data": None}


# ---------------------------------------------------------------------------
# V1.3：整单测试结果上传（机台主接口）
# ---------------------------------------------------------------------------
@router.post("/api/v1/test-results")
async def post_test_results_v1(
    payload: TestResultUploadIn,
):
    """整单测试结果上报；按协议返回 {success,code,message,data} 信封。"""
    try:
        data = upload_execute(
            payload=payload.model_dump(),
            headers={},
            report_one=services.report_test_result,
        )
    except UploadValidationError as exc:
        return JSONResponse(status_code=200, content=_envelope(False, "测试报告上传失败", "400"))
    except UploadConflictError as exc:
        return JSONResponse(status_code=200, content=_envelope(False, "测试报告上传失败", "400"))
    except Exception as exc:
        return JSONResponse(status_code=200, content=_envelope(False, "测试报告上传失败", "400"))

    return _envelope(True, "测试报告上次成功", "200")
