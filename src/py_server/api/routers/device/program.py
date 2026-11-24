"""程序下发 / 可信性路由。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from .... import config, db, services
from ....repositories.program_files import resolve_download
from ...schemas import BindingsIn, ProgramStatusIn
from fastapi.responses import FileResponse

router = APIRouter(tags=["program"])


@router.get("/health")
def health() -> dict:
    """执行 health。"""
    return {"status": "ok", "time": db.utc_now_iso(), "database": str(config.db_path())}


@router.get("/programs/{filename}")
def download_program_file(filename: str) -> FileResponse:
    """执行 download_program_file。"""
    target = resolve_download(filename)
    if target is None:
        from ....services import NotFoundError

        raise NotFoundError("程序文件不存在")
    return FileResponse(target, filename=target.name)


@router.get("/api/program")
def get_program(
    device_id: str = Query(..., min_length=1),
    product: str | None = Query(default=None),
) -> dict:
    """获取program。"""
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


@router.post("/api/program/status")
def post_program_status(payload: ProgramStatusIn) -> dict:
    """执行 post_program_status。"""
    return services.report_program_status(
        device_id=payload.device_id,
        product=payload.product,
        reported_version=payload.program_version,
        reported_sha256=payload.sha256,
        sha256_ok=payload.sha256_ok,
    )


# --- UI 只读/配置接口 ---
@router.get("/api/ui/bindings")
def ui_list_bindings() -> list[dict]:
    """执行 ui_list_bindings。"""
    return services.list_bindings()


@router.post("/api/ui/bindings")
def ui_replace_bindings(payload: BindingsIn) -> dict:
    """执行 ui_replace_bindings。"""
    return {"count": services.replace_bindings(payload.rows)}


@router.get("/api/ui/program/drift")
def ui_program_drift() -> list[dict]:
    """执行 ui_program_drift。"""
    return services.program_drift()


@router.get("/api/ui/program/pulls")
def ui_program_pulls(limit: int = 30) -> list[dict]:
    """执行 ui_program_pulls。"""
    return services.list_program_pulls(limit)


@router.get("/api/ui/program/status-logs")
def ui_program_status_logs(limit: int = 30) -> list[dict]:
    """执行 ui_program_status_logs。"""
    return services.list_program_status_logs(limit)


@router.post("/api/ui/program/publish")
async def ui_publish_program(device_id: str, product: str, program_version: str, file) -> dict:
    """执行 ui_publish_program。"""
    content = await file.read()
    return services.publish_program_file(
        device_id=device_id,
        product=product,
        program_version=program_version,
        filename=file.filename or "program.bin",
        content=content,
    )