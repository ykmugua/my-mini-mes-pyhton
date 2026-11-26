"""产品查询、追溯与工位操作台接口。

路由保持很薄：参数声明 + 调用 service/repository；跨库扫描与数据组装在
repositories/report_query_store.py，业务校验在 services/application。
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from .... import services
from ....repositories import active_product_repo, master_data_repo, product_flow_store, report_query_store
from ....services import NotFoundError
from ...schemas_workbench import WorkpieceDownlineIn
from ...schemas import WorkbenchInboundIn, WorkbenchTrayUnbindIn

router = APIRouter(tags=["product_query"])


@router.get("/api/ui/product/options")
def ui_product_options() -> list[str]:
    """执行 ui_product_options。"""
    return services.distinct_products()


@router.get("/api/ui/product/workpieces")
def ui_query_workpieces(
    product: str | None = Query(default=None),
    workpiece: str | None = Query(default=None),
    device: str | None = Query(default=None),
    board_status: str | None = Query(default=None),
    current_step: str | None = Query(default=None),
    test_step: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    limit: int = Query(default=200),
) -> list[dict]:
    """执行 ui_query_workpieces。"""
    return services.query_workpieces(
        product=product, workpiece=workpiece, device=device,
        board_status=board_status, current_step=current_step, test_step=test_step,
        date_from=date_from, date_to=date_to, limit=limit,
    )


@router.get("/api/ui/product/workpiece/{workpiece}/detail")
def ui_workpiece_detail(workpiece: str) -> dict:
    """执行 ui_workpiece_detail。"""
    data = services.workpiece_detail(workpiece)
    if data is None:
        raise NotFoundError(f"工件 {workpiece} 不存在")
    return data


@router.get("/api/ui/product/workpiece/{workpiece}/history")
def ui_workpiece_history(workpiece: str) -> dict:
    """执行 ui_workpiece_history。"""
    return {
        "tests": services.workpiece_test_history(workpiece),
        "unlocks": services.workpiece_unlock_history(workpiece),
    }


@router.get("/api/ui/product/route/{product_model}")
def ui_product_route(product_model: str) -> dict:
    """执行 ui_product_route。"""
    return services.product_route_detail(product_model)


@router.get("/api/ui/product/report-index")
def ui_report_index(
    barcode: str | None = Query(default=None),
    step_no: str | None = Query(default=None),
) -> list[dict]:
    """执行 ui_report_index。"""
    return report_query_store.list_report_index(barcode=barcode, step_no=step_no)


@router.get("/api/ui/product/report-details")
def ui_report_details(
    table: str = Query(min_length=3),
    step_no: str | None = Query(default=None),
) -> list[dict]:
    """按总览表给出的表名读取明细（表名格式在 repository 内校验）。"""
    return report_query_store.list_details(table, step_no=step_no)


@router.get("/api/ui/product/report-traycodes")
def ui_report_traycodes() -> list[dict]:
    """按产品条码返回最后一次测试上报的托盘码（产品查询展示用）。"""
    return report_query_store.latest_traycodes()


@router.get("/api/ui/product/report-filter-options")
def ui_report_filter_options() -> dict:
    """测试报告筛选选项：产品/条码/托盘来自工序报告库。"""
    return report_query_store.filter_options()


@router.get("/api/ui/product/report-query")
def ui_report_query(
    product: str | None = Query(default=None),
    step_no: str | None = Query(default=None),
    barcode: str | None = Query(default=None),
    traycode: str | None = Query(default=None),
    fixturecode: str | None = Query(default=None),
    result: str | None = Query(default=None),
    board_status: str | None = Query(default=None),
    current_step: str | None = Query(default=None),
    last_report_device: str | None = Query(default=None),
    limit: int = Query(default=200),
) -> list[dict]:
    """按产品型号 + 测试工序直接查询对应工序库的 report_index。"""
    return report_query_store.query_reports(
        product=product,
        step_no=step_no,
        barcode=barcode,
        traycode=traycode,
        fixturecode=fixturecode,
        result=result,
        board_status=board_status,
        current_step=current_step,
        last_report_device=last_report_device,
        limit=limit,
    )


@router.get("/api/ui/product/flow-overview")
def ui_product_flow_overview(
    barcode: str | None = Query(default=None),
    componentcode: str | None = Query(default=None),
    traycode: str | None = Query(default=None),
    device: str | None = Query(default=None),
    board_status: str | None = Query(default=None),
    current_step: str | None = Query(default=None),
) -> list[dict]:
    """执行 ui_product_flow_overview。"""
    return product_flow_store.list_overview(
        barcode=barcode, componentcode=componentcode, traycode=traycode, device=device,
        board_status=board_status, current_step=current_step,
    )


@router.get("/api/ui/product/active-products")
def ui_list_active_products(
    barcode: str | None = Query(default=None),
    traycode: str | None = Query(default=None),
) -> list[dict]:
    """列出 mes.db 中维护的当前在制产品。"""
    return active_product_repo.list_active(barcode=barcode, traycode=traycode)


@router.get("/api/ui/product/flow-details")
def ui_product_flow_details(flow_table: str = Query(min_length=3)) -> list[dict]:
    """执行 ui_product_flow_details。"""
    return product_flow_store.list_flow(flow_table)


@router.delete("/api/ui/product/flow")
def ui_delete_product_flow(barcode: str = Query(min_length=1)) -> dict:
    """执行 ui_delete_product_flow。"""
    return services.delete_product_flow(barcode=barcode)


@router.delete("/api/ui/product/tray-flow")
def ui_delete_tray_flow(traycode: str = Query(min_length=1)) -> dict:
    """执行 ui_delete_tray_flow。"""
    return services.delete_tray_flow(traycode=traycode)


@router.post("/api/ui/product/repair-tray-report-fields")
def ui_repair_tray_report_fields() -> dict:
    """执行 ui_repair_tray_report_fields。"""
    return services.repair_tray_operation_report_fields()


@router.get("/api/ui/product/step-options")
def ui_step_options() -> list[dict]:
    """执行 ui_step_options。"""
    return master_data_repo.list_steps()


@router.get("/api/ui/workbench/recipe")
def ui_workbench_recipe(product: str = Query(min_length=1), process_code: str | None = Query(default=None)) -> dict:
    """执行 ui_workbench_recipe。"""
    return services.workbench_recipe(product, process_code)


@router.get("/api/ui/workbench/processes")
def ui_workbench_processes(product: str = Query(min_length=1)) -> list[dict]:
    """列出产品型号下已启用的工艺。"""
    return services.workbench_processes(product)


@router.post("/api/ui/workbench/inbound")
def ui_workbench_inbound(payload: WorkbenchInboundIn) -> dict:
    """执行 ui_workbench_inbound。"""
    return services.manual_inbound(
        product=payload.product,
        process_code=payload.process_code,
        step_no=payload.step_no,
        traycode=payload.traycode,
        barcodes=payload.barcodes,
        operator=payload.operator,
    )


@router.post("/api/ui/workbench/workpiece-downline")
def ui_workpiece_downline(payload: WorkpieceDownlineIn) -> dict:
    """执行 ui_workpiece_downline。"""
    return services.downline_workpiece(
        barcode=payload.barcode,
        operator=payload.operator,
        confirmed=payload.confirmed,
    )


@router.post("/api/ui/workbench/tray-unbind")
def ui_workbench_tray_unbind(payload: WorkbenchTrayUnbindIn) -> dict:
    """执行 ui_workbench_tray_unbind。"""
    return services.unbind_tray(
        traycode=payload.traycode,
        operator=payload.operator,
        confirmed=payload.confirmed,
    )
