"""主数据接口：工序/设备/程序/组件/工艺（供页面使用）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ....repositories import master_data_repo
from ....repositories.base import with_conn
from ...schemas import MasterDataIn

router = APIRouter(tags=["master_data"])

# 单项读：直接返回列表（页面只需 init 时拉一次全量）
@router.get("/api/ui/master")
def get_master() -> dict:
    """获取master。"""
    return master_data_repo.snapshot()


@router.get("/api/ui/program-history")
def get_program_history(name: str) -> list[dict]:
    """获取program_history。"""
    return master_data_repo.list_program_history(name)


@router.delete("/api/ui/program-version/{program_id}")
def delete_program_version(program_id: int) -> dict:
    """删除program_version。"""
    from ....repositories.base import with_conn

    with with_conn() as conn:
        deleted = master_data_repo.delete_program_version(conn, program_id)
    if deleted is None:
        from ....services import NotFoundError

        raise NotFoundError(f"程序版本 {program_id} 不存在")
    return {"deleted": deleted}


@router.get("/api/ui/master/{key}")
def get_master_key(key: str) -> list[dict]:
    """获取master_key。"""
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
        from ....services import NotFoundError

        raise NotFoundError(f"未知主数据类型 {key}")
    return getters[key]()


@router.post("/api/ui/master/{key}")
def save_master_key(key: str, payload: MasterDataIn) -> dict:
    """保存master_key。"""
    old_rows: list[dict] = []
    if key in {"products", "programs", "processes"}:
        with with_conn() as conn:
            if key == "products":
                old_rows = master_data_repo.list_products(conn)
            elif key == "programs":
                old_rows = master_data_repo.list_programs(conn)
            else:
                old_rows = master_data_repo.list_processes(conn)
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
        from ....services import NotFoundError

        raise NotFoundError(f"未知主数据类型 {key}")
    with with_conn() as conn:
        setters[key](conn, payload.rows)
        if key == "products":
            renames = {
                str(old.get("product_model") or ""): str(new.get("product_model") or "")
                for old, new in zip(old_rows, payload.rows)
                if old.get("product_model") and new.get("product_model")
                and str(old.get("product_model")) != str(new.get("product_model"))
            }
            processes = master_data_repo.list_processes(conn)
            changed = False
            for process in processes:
                component = str(process.get("component_no") or "")
                if component in renames:
                    process["component_no"] = renames[component]
                    changed = True
            if changed:
                master_data_repo.replace_processes(conn, processes)
            from sqlalchemy import update

            from ....engine import program_bindings

            for old, new in renames.items():
                conn.execute(
                    update(program_bindings)
                    .where(program_bindings.c.product == old)
                    .values(product=new)
                )
        elif key == "programs":
            renames = {
                str(old.get("program_name") or ""): str(new.get("program_name") or "")
                for old, new in zip(old_rows, payload.rows)
                if old.get("program_name") and new.get("program_name")
                and str(old.get("program_name")) != str(new.get("program_name"))
            }
            for old, new in renames.items():
                from sqlalchemy import update

                from ...engine import process_step_resources

                conn.execute(
                    update(process_step_resources)
                    .where(process_step_resources.c.program_name == old)
                    .values(program_name=new)
                )
        elif key == "processes":
            renames = {
                str(old.get("process_code") or ""): str(new.get("process_code") or "")
                for old, new in zip(old_rows, payload.rows)
                if old.get("process_code") and new.get("process_code")
                and str(old.get("process_code")) != str(new.get("process_code"))
            }
            routes = master_data_repo.list_process_routes(conn)
            resources = master_data_repo.list_process_step_resources(conn)
            route_changed = resource_changed = False
            for row in routes:
                code = str(row.get("process_code") or "")
                if code in renames:
                    row["process_code"] = renames[code]
                    route_changed = True
            for row in resources:
                code = str(row.get("process_code") or "")
                if code in renames:
                    row["process_code"] = renames[code]
                    resource_changed = True
            if route_changed:
                master_data_repo.replace_process_routes(conn, routes)
            if resource_changed:
                master_data_repo.replace_process_step_resources(conn, resources)
    if key == "products":
        from ....repositories import product_flow_store

        for old, new in renames.items():
            product_flow_store.rename_componentcode(old, new)
    return {"count": len(payload.rows)}
