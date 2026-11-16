"""开放性变量路由。"""

from __future__ import annotations

from fastapi import APIRouter

from ... import services
from ..schemas import VariableCreateIn, VariableWriteIn

router = APIRouter(tags=["variable"])


@router.get("/api/variable/{name}")
def get_variable(name: str) -> dict:
    return services.get_variable(name)


@router.post("/api/variable/{name}")
def post_variable(name: str, payload: VariableWriteIn) -> dict:
    return services.set_variable(name=name, value=payload.value, device_id=payload.device_id)


@router.get("/api/ui/variables")
def ui_variables(prefix: str = "") -> list[dict]:
    return services.list_variables(prefix)


@router.post("/api/ui/variables")
def ui_add_variable(payload: VariableCreateIn) -> dict:
    return services.add_variable(payload.name, payload.type, payload.value)