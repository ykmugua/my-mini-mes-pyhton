"""开放性变量路由。"""

from __future__ import annotations

from fastapi import APIRouter

from ... import services
from fastapi import Query
from ..schemas import VariableCreateIn, VariableRenameIn, VariableUpdateIn, VariableWriteIn

router = APIRouter(tags=["variable"])


@router.get("/api/variable/{name}")
def get_variable(name: str, device_id: str | None = None) -> dict:
    """获取variable。"""
    return services.get_variable(name, device_id=device_id)


@router.post("/api/variable/{name}")
def post_variable(name: str, payload: VariableWriteIn) -> dict:
    """执行 post_variable。"""
    return services.set_variable(name=name, value=payload.value, device_id=payload.device_id)


@router.delete("/api/ui/variables/{name}")
def ui_delete_variable(name: str) -> dict:
    """执行 ui_delete_variable。"""
    return services.delete_variable(name)


@router.put("/api/ui/variables/{name}")
def ui_rename_variable(name: str, payload: VariableRenameIn) -> dict:
    """执行 ui_rename_variable。"""
    return services.rename_variable(name, payload.name)


@router.patch("/api/ui/variables/{name}")
def ui_update_variable(name: str, payload: VariableUpdateIn) -> dict:
    """执行 ui_update_variable。"""
    return services.update_variable_def(name, type_name=payload.type, value=payload.value)


@router.get("/api/ui/variables/tree")
def ui_variables_tree(prefix: str = "") -> dict:
    """执行 ui_variables_tree。"""
    return services.variables_tree_from_api(prefix)


@router.get("/api/ui/variables")
def ui_variables(prefix: str = "") -> list[dict]:
    """执行 ui_variables。"""
    return services.list_variables(prefix)


@router.post("/api/ui/variables")
def ui_add_variable(payload: VariableCreateIn) -> dict:
    """执行 ui_add_variable。"""
    return services.add_variable(payload.name, payload.type, payload.value)

@router.get("/api/ui/variable-logs/read")
def ui_variable_read_logs(limit: int = 30) -> list[dict]:
    """执行 ui_variable_read_logs。"""
    return services.list_variable_logs(action="READ", limit=limit)


@router.get("/api/ui/variable-logs/write")
def ui_variable_write_logs(limit: int = 30) -> list[dict]:
    """执行 ui_variable_write_logs。"""
    return services.list_variable_logs(action="WRITE", limit=limit)
