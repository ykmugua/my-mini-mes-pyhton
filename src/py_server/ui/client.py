"""唯一的 HTTP 客户端：Streamlit 进程只通过它访问 FastAPI，不碰数据库。

失败降级：请求超时（3s）或报错时返回上次成功数据 + 错误提示。
"""

from __future__ import annotations

from typing import Any

import httpx

from .. import config

TIMEOUT_SECONDS = 3.0

# session_state key -> HTTP endpoint / params builder
_FALLBACK: dict[str, Any] = {}


class ApiError(Exception):
    """HTTP 调用失败（超时、连接错误或 4xx/5xx）。"""


def base_url() -> str:
    return config.ui_api_base()


def _request(method: str, path: str, **kwargs) -> Any:
    # 测试模式：AppTest 无独立 FastAPI 进程时，允许用 TestClient 进程内转发。
    # 仍走 HTTP 语义（同一套接口与序列化），只是不做真实网络监听。
    import os

    if os.environ.get("MES_UI_INPROCESS") == "1":
        from fastapi.testclient import TestClient

        from ..api import app

        with TestClient(app) as tc:
            response = tc.request(method, path, **kwargs)
        if response.status_code >= 400:
            raise ApiError(f"接口 {method} {path} 失败（{response.status_code}）：{response.text}")
        return response.json() if response.content else None

    url = f"{base_url()}{path}"
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
            response = client.request(method, url, **kwargs)
    except httpx.HTTPError as exc:
        raise ApiError(f"无法连接接口服务 {url}：{exc}") from exc
    if response.status_code >= 400:
        detail = response.text
        try:
            detail = response.json().get("detail", detail)
        except ValueError:
            pass
        raise ApiError(f"接口 {method} {path} 失败（{response.status_code}）：{detail}")
    if response.status_code == 204:
        return None
    return response.json()


# -----------------------------------------------------------------------------
# 只读数据（带 session_state 降级）
# -----------------------------------------------------------------------------
def _cached_get(cache_key: str, path: str, params: dict | None = None) -> tuple[Any, str | None]:
    """返回 (data, error)。失败时返回上次成功数据并记录错误。"""
    import streamlit as st

    try:
        data = _request("GET", path, params=params)
        st.session_state[f"ui_cache_{cache_key}"] = data
        st.session_state.pop(f"ui_error_{cache_key}", None)
        return data, None
    except ApiError as exc:
        cached = st.session_state.get(f"ui_cache_{cache_key}")
        st.session_state[f"ui_error_{cache_key}"] = str(exc)
        return cached, str(exc)


def list_bindings() -> tuple[list[dict], str | None]:
    return _cached_get("bindings", "/api/ui/bindings")


def program_drift() -> tuple[list[dict], str | None]:
    return _cached_get("drift", "/api/ui/program/drift")


def list_program_pulls(limit: int = 30) -> tuple[list[dict], str | None]:
    return _cached_get(f"pulls_{limit}", "/api/ui/program/pulls", {"limit": limit})


def list_program_status_logs(limit: int = 30) -> tuple[list[dict], str | None]:
    return _cached_get(f"status_logs_{limit}", "/api/ui/program/status-logs", {"limit": limit})


def list_locked_workpieces() -> tuple[list[dict], str | None]:
    return _cached_get("locked", "/api/ui/workpieces/locked")


def list_unlock_logs(limit: int = 50) -> list[dict] | None:
    data, _ = _cached_get(f"unlock_logs_{limit}", "/api/ui/unlock-logs", {"limit": limit})
    return data


def list_upstream_rules() -> tuple[list[dict], str | None]:
    return _cached_get("upstream", "/api/ui/upstream")


def interlock_check(workpiece: str, device_id: str | None, product: str | None) -> dict:
    return _request(
        "GET",
        "/api/interlock",
        params={"workpiece": workpiece, "device_id": device_id, "product": product},
    )


def list_devices() -> tuple[list[str], str | None]:
    return _cached_get("devices", "/api/ui/devices")


def dashboard_snapshot(device_filter: str | None = None) -> tuple[dict | None, str | None]:
    return _cached_get(
        f"dashboard_{device_filter or 'all'}",
        "/api/ui/dashboard",
        {"device": device_filter} if device_filter else None,
    )


def variables_tree(prefix: str = "") -> tuple[dict | None, str | None]:
    return _cached_get(f"variables_tree_{prefix}", "/api/ui/variables/tree", {"prefix": prefix})


def list_variables(prefix: str = "") -> tuple[list[dict], str | None]:
    return _cached_get(f"variables_{prefix}", "/api/ui/variables", {"prefix": prefix})


def get_variable(name: str) -> dict:
    return _request("GET", f"/api/variable/{name}")


# -----------------------------------------------------------------------------
# 写操作（不做降级：失败必须报错）
# -----------------------------------------------------------------------------
def replace_bindings(rows: list[dict]) -> int:
    return _request("POST", "/api/ui/bindings", json={"rows": rows})["count"]


def publish_program_file(device_id: str, product: str, program_version: str,
                         filename: str, content: bytes) -> dict:
    return _request(
        "POST",
        "/api/ui/program/publish",
        data={"device_id": device_id, "product": product, "program_version": program_version},
        files={"file": (filename, content)},
    )


def replace_upstream_rules(rows: list[dict]) -> int:
    return _request("POST", "/api/ui/upstream", json={"rows": rows})["count"]


def unlock_workpiece(workpiece: str, operator: str, reason: str, confirmed: bool, target_step: str | None = None, note: str | None = None) -> dict:
    return _request(
        "POST",
        "/api/ui/unlock",
        json={
            "workpiece": workpiece, "operator": operator, "reason": reason,
            "target_step": target_step, "note": note, "confirmed": confirmed,
        },
    )


def add_variable(name: str, type_name: str, value: Any) -> dict:
    return _request(
        "POST", "/api/ui/variables", json={"name": name, "type": type_name, "value": value}
    )


def set_variable(name: str, value: Any, device_id: str) -> dict:
    return _request("POST", f"/api/variable/{name}", json={"value": value, "device_id": device_id})


def delete_variable(name: str) -> dict:
    return _request("DELETE", f"/api/ui/variables/{name}")


def rename_variable(old_name: str, new_name: str) -> dict:
    return _request("PUT", f"/api/ui/variables/{old_name}", json={"name": new_name})


def update_variable_def(name: str, *, type_name: str, value: Any) -> dict:
    return _request("PATCH", f"/api/ui/variables/{name}", json={"type": type_name, "value": value})

# -----------------------------------------------------------------------------
# 主数据（app_pages 页面）
# -----------------------------------------------------------------------------
MASTER_KEYS = (
    "steps", "devices", "programs", "program_versions",
    "products", "processes", "process_routes", "process_step_resources",
)


def master_snapshot() -> tuple[dict, str | None]:
    return _cached_get("master", "/api/ui/master")


def master_list(key: str) -> list[dict]:
    return _request("GET", f"/api/ui/master/{key}")


def master_save(key: str, rows: list[dict]) -> int:
    return _request("POST", f"/api/ui/master/{key}", json={"rows": rows})["count"]


def program_history(name: str) -> list[dict]:
    return _request("GET", "/api/ui/program-history", params={"name": name})


def delete_program_version(program_id: int) -> dict:
    return _request("DELETE", f"/api/ui/program-version/{program_id}")


def variable_logs(action: str, limit: int = 30) -> list[dict]:
    return _request("GET", f"/api/ui/variable-logs/{action}", params={"limit": limit})


# -----------------------------------------------------------------------------
# 产品查询/追溯（只读；解绑用 unlock_workpiece）
# -----------------------------------------------------------------------------
def product_options() -> list[str]:
    return _request("GET", "/api/ui/product/options")


def query_workpieces(**params) -> list[dict]:
    return _request("GET", "/api/ui/product/workpieces", params=params)


def workpiece_detail(workpiece: str) -> dict:
    return _request("GET", f"/api/ui/product/workpiece/{workpiece}/detail")


def step_options() -> list[dict]:
    return _request("GET", "/api/ui/product/step-options")


def report_index(barcode: str | None = None, step_no: str | None = None) -> list[dict]:
    params = {}
    if barcode:
        params["barcode"] = barcode
    if step_no:
        params["step_no"] = step_no
    return _request("GET", "/api/ui/product/report-index", params=params or None)


def report_details(table: str, step_no: str | None = None) -> list[dict]:
    params = {"table": table}
    if step_no:
        params["step_no"] = step_no
    return _request("GET", "/api/ui/product/report-details", params=params)


def product_flow_overview(
    barcode: str | None = None,
    componentcode: str | None = None,
    traycode: str | None = None,
    device: str | None = None,
    board_status: str | None = None,
    current_step: str | None = None,
) -> list[dict]:
    params = {}
    if barcode:
        params["barcode"] = barcode
    if componentcode:
        params["componentcode"] = componentcode
    if traycode:
        params["traycode"] = traycode
    if device:
        params["device"] = device
    if board_status:
        params["board_status"] = board_status
    if current_step:
        params["current_step"] = current_step
    return _request("GET", "/api/ui/product/flow-overview", params=params or None)


def product_flow_details(flow_table: str) -> list[dict]:
    return _request("GET", "/api/ui/product/flow-details", params={"flow_table": flow_table})


def workpiece_history(workpiece: str) -> dict:
    return _request("GET", f"/api/ui/product/workpiece/{workpiece}/history")


def product_route(product_model: str) -> dict:
    return _request("GET", f"/api/ui/product/route/{product_model}")
