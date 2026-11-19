"""主数据接口：工序/线体/设备/程序/产品（供 app_pages 页面使用）。"""

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
        "lines": master_data_repo.list_lines,
        "devices": master_data_repo.list_devices,
        "trays": master_data_repo.list_trays,
        "programs": master_data_repo.list_programs,
        "program_versions": master_data_repo.list_program_versions,
        "program_components": master_data_repo.list_program_components,
        "products": master_data_repo.list_products,
        "product_routes": master_data_repo.list_product_routes,
        "product_step_devices": master_data_repo.list_product_step_devices,
    }
    if key not in getters:
        from ...services import NotFoundError

        raise NotFoundError(f"未知主数据类型 {key}")
    return getters[key]()


@router.post("/api/ui/master/{key}")
def save_master_key(key: str, payload: MasterDataIn) -> dict:
    setters = {
        "steps": master_data_repo.replace_steps,
        "lines": master_data_repo.replace_lines,
        "devices": master_data_repo.replace_devices,
        "trays": master_data_repo.replace_trays,
        "programs": master_data_repo.replace_programs,
        "program_versions": master_data_repo.replace_program_versions,
        "program_components": master_data_repo.replace_program_components,
        "products": master_data_repo.replace_products,
        "product_routes": master_data_repo.replace_product_routes,
        "product_step_devices": master_data_repo.replace_product_step_devices,
    }
    if key not in setters:
        from ...services import NotFoundError

        raise NotFoundError(f"未知主数据类型 {key}")
    with with_conn() as conn:
        setters[key](conn, payload.rows)
    return {"count": len(payload.rows)}