"""FastAPI 应用实例：异常处理、静态目录挂载、路由注册。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .. import config, db
from .routers import dashboard, interlock, master_data, program, test_result, variable
from ..services import ServiceError


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


app.include_router(program.router)
app.include_router(test_result.router)
app.include_router(interlock.router)
app.include_router(variable.router)
app.include_router(dashboard.router)
app.include_router(master_data.router)