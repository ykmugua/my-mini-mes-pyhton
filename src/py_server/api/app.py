"""FastAPI 应用实例：异常处理、静态目录挂载、路由注册。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .. import config, db
from .routers.common import interlock, variable
from .routers.device import control, program, test_result
from .routers.ui import dashboard, master_data, product_query
from ..services import ServiceError


@asynccontextmanager
async def lifespan(_: FastAPI):
    """执行 lifespan。"""
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
    """执行 service_error_handler。"""
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


# 设备接口
app.include_router(control.router)
app.include_router(program.router)
app.include_router(test_result.router)
# 共同接口
app.include_router(interlock.router)
app.include_router(variable.router)
# UI 接口
app.include_router(dashboard.router)
app.include_router(master_data.router)
app.include_router(product_query.router)
