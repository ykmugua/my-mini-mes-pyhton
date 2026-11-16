"""测试结果上报路由。"""

from __future__ import annotations

from fastapi import APIRouter

from ... import services
from ..schemas import TestResultIn

router = APIRouter(tags=["test_result"])


@router.post("/api/test-result")
def post_test_result(payload: TestResultIn) -> dict:
    return services.report_test_result(
        workpiece=payload.workpiece,
        device_id=payload.device_id,
        test_item=payload.test_item,
        result=payload.result,
        measured_value=payload.measured_value,
        program_version=payload.program_version,
        program_sha256=payload.program_sha256,
        product=payload.product,
        tested_at=payload.tested_at,
    )