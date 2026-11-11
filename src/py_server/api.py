"""设备侧 HTTP 接口（FastAPI 独立服务）。

启动方式::

    uvicorn py_server.api:app --host 0.0.0.0 --port 8000

接口清单
--------
GET  /api/program?device_id=&product=   拉取程序元数据（同时记录拉取日志）
POST /api/program/status                上报已加载版本与校验结果
POST /api/test-result                   上报测试结果（幂等）
GET  /api/interlock?workpiece=&device_id= 查询工件放行状态
GET  /api/variable/{name}               读取开放变量
POST /api/variable/{name}               写入开放变量
GET  /health                            健康检查
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import AliasChoices, BaseModel, Field, field_validator

from . import config, db, services
from .services import NotFoundError, ServiceError


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    config.program_dir()
    yield


app = FastAPI(
    title="旁路式小型 MES · 设备接口",
    version="0.1.0",
    description="设备乙方内部使用：程序下发、测试结果上报、工序锁、开放变量。",
    lifespan=lifespan,
)


@app.exception_handler(ServiceError)
async def service_error_handler(_: Request, exc: ServiceError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


# -----------------------------------------------------------------------------
# 请求模型
# -----------------------------------------------------------------------------
class ProgramStatusIn(BaseModel):
    device_id: str = Field(min_length=1)
    product: str | None = None
    program_version: str | None = Field(
        default=None,
        validation_alias=AliasChoices("program_version", "version", "reported_version"),
    )
    sha256: str | None = Field(
        default=None,
        validation_alias=AliasChoices("sha256", "program_sha256", "reported_sha256"),
    )
    sha256_ok: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("sha256_ok", "checksum_ok", "verified"),
    )
    reported_at: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("reported_at", "timestamp", "loaded_at"),
    )


class TestResultIn(BaseModel):
    workpiece: str = Field(
        min_length=1,
        validation_alias=AliasChoices("workpiece", "workpiece_code", "workpiece_id"),
    )
    device_id: str = Field(min_length=1)
    test_item: str = Field(min_length=1)
    result: str
    measured_value: str | float | int | None = None
    program_version: str | None = None
    program_sha256: str | None = Field(
        default=None,
        validation_alias=AliasChoices("program_sha256", "sha256"),
    )
    product: str | None = None
    tested_at: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("tested_at", "timestamp", "ts"),
    )

    @field_validator("result")
    @classmethod
    def _normalize_result(cls, value: str) -> str:
        value = (value or "").strip().upper()
        if value not in ("PASS", "FAIL"):
            raise ValueError("result 只能是 PASS 或 FAIL")
        return value


class VariableWriteIn(BaseModel):
    value: Any = None
    device_id: str = Field(
        min_length=1,
        validation_alias=AliasChoices("device_id", "device", "writer"),
    )


# -----------------------------------------------------------------------------
# 接口
# -----------------------------------------------------------------------------
@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "time": db.utc_now_iso(),
        "database": str(config.db_path()),
    }


@app.get("/programs/{filename}")
def download_program_file(filename: str) -> FileResponse:
    """程序文件静态下载（只允许访问程序目录内的文件）。"""
    root = config.program_dir().resolve()
    target = (root / Path(filename).name).resolve()
    if target.parent != root or not target.is_file():
        raise NotFoundError("程序文件不存在")
    return FileResponse(target, filename=target.name)


@app.get("/api/program")
def get_program(
    device_id: str = Query(..., min_length=1),
    product: str | None = Query(default=None),
) -> dict:
    binding = services.record_program_pull(device_id, product)
    return {
        "device_id": binding["device_id"],
        "product": binding["product"],
        "program_version": binding["program_version"],
        "download_url": binding["download_url"],
        "sha256": binding["sha256"],
        "last_pull_at": binding["last_pull_at"],
        "server_time": db.utc_now_iso(),
    }


@app.post("/api/program/status")
def post_program_status(payload: ProgramStatusIn) -> dict:
    return services.report_program_status(
        device_id=payload.device_id,
        product=payload.product,
        reported_version=payload.program_version,
        reported_sha256=payload.sha256,
        sha256_ok=payload.sha256_ok,
    )


@app.post("/api/test-result")
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


@app.get("/api/interlock")
def get_interlock(
    workpiece: str = Query(..., min_length=1),
    device_id: str | None = Query(default=None),
    product: str | None = Query(default=None),
) -> dict:
    return services.interlock_check(workpiece=workpiece, device_id=device_id, product=product)


@app.get("/api/variable/{name}")
def get_variable(name: str) -> dict:
    return services.get_variable(name)


@app.post("/api/variable/{name}")
def post_variable(name: str, payload: VariableWriteIn) -> dict:
    return services.set_variable(
        name=name,
        value=payload.value,
        device_id=payload.device_id,
    )


if __name__ == "__main__":
    uvicorn.run(
        "py_server.api:app",
        host=os.environ.get("MES_API_HOST", "0.0.0.0"),
        port=config.api_port(),
        reload=False,
    )
