"""产品进站校验设备接口：只读校验，不改变任何业务状态。"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ...schemas_checkin import WorkpieceCheckInIn, WorkpieceCheckInOut
from ....application.workpiece_check_in import CheckInRequest, execute

router = APIRouter(tags=["device"])


@router.post("/api/workpiece/check-in", response_model=WorkpieceCheckInOut)
def check_in(payload: WorkpieceCheckInIn) -> WorkpieceCheckInOut | JSONResponse:
    """校验产品是否允许在指定工位进站；业务失败以 HTTP 200 的 success=false 表示。"""
    try:
        result = execute(CheckInRequest(
            barcode=payload.barcode,
            station=payload.station,
            fixturecode=payload.fixturecode,
            traycode=payload.traycode,
        ))
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "code": "500",
                "message": f"产品进站失败：MES 内部异常：{exc}",
                "data": None,
            },
        )
    return WorkpieceCheckInOut(**result.envelope())
