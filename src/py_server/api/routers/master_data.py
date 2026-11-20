"""主数据接口：工序/设备/程序/组件/工艺（供页面使用）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ...repositories import master_data_repo
from ...repositories.base import with_conn
from ..schemas import MasterDataIn

router = APIRouter(tags=["master_data"])

# 单项读：直接返回列表（页面只需 init 时拉一次全量）
@router.get("/api/ui/master")
def get_master() -> dict:
    return master_data_repo.snapshot()


@router.get("/api/ui/program-history")
def get_program_history(name: str) -> list[dict]:
    return master_data_repo.list_program_history(name)


@router.delete("/api/ui/program-version/{program_id}")
def delete_program_version(program_id: int) -> dict:
    from ...repositories.base import with_conn

    with with_conn() as conn:
        deleted = master_data_repo.delete_program_version(conn, program_id)
    if deleted is None:
        from ...services import NotFoundError

        raise NotFoundError(f"程序版本 {program_id} 不存在")
    return {"deleted": deleted}


@router.get("/api/ui/master/{key}")
def get_master_key(key: str) -> list[dict]:
    getters = {
        "steps": master_data_repo.list_steps,
        "devices": master_data_repo.list_devices,
        "trays": master_data_repo.list_trays,
        "programs": master_data_repo.list_programs,
        "program_versions": master_data_repo.list_program_versions,
        "products": master_data_repo.list_products,
        "processes": master_data_repo.list_processes,
        "process_routes": master_data_repo.list_process_routes,
        "process_step_resources": master_data_repo.list_process_step_resources,
    }
    if key not in getters:
        from ...services import NotFoundError

        raise NotFoundError(f"未知主数据类型 {key}")
    return getters[key]()


@router.post("/api/ui/master/{key}")
def save_master_key(key: str, payload: MasterDataIn) -> dict:
    setters = {
        "steps": master_data_repo.replace_steps,
        "devices": master_data_repo.replace_devices,
        "trays": master_data_repo.replace_trays,
        "programs": master_data_repo.replace_programs,
        "program_versions": master_data_repo.replace_program_versions,
        "products": master_data_repo.replace_products,
        "processes": master_data_repo.replace_processes,
        "process_routes": master_data_repo.replace_process_routes,
        "process_step_resources": master_data_repo.replace_process_step_resources,
    }
    if key not in setters:
        from ...services import NotFoundError

        raise NotFoundError(f"未知主数据类型 {key}")
    with with_conn() as conn:
        setters[key](conn, payload.rows)
    return {"count": len(payload.rows)}