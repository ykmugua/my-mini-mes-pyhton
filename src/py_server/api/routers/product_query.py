"""产品查询与追溯接口（只读查询；解绑复用 interlock 的 unlock）。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from ... import services

router = APIRouter(tags=["product_query"])


@router.get("/api/ui/product/options")
def ui_product_options() -> list[str]:
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
    return services.query_workpieces(
        product=product, workpiece=workpiece, device=device,
        board_status=board_status, current_step=current_step, test_step=test_step,
        date_from=date_from, date_to=date_to, limit=limit,
    )


@router.get("/api/ui/product/workpiece/{workpiece}/detail")
def ui_workpiece_detail(workpiece: str) -> dict:
    data = services.workpiece_detail(workpiece)
    if data is None:
        from ...services import NotFoundError
        raise NotFoundError(f"工件 {workpiece} 不存在")
    return data


@router.get("/api/ui/product/workpiece/{workpiece}/history")
def ui_workpiece_history(workpiece: str) -> dict:
    return {
        "tests": services.workpiece_test_history(workpiece),
        "unlocks": services.workpiece_unlock_history(workpiece),
    }


@router.get("/api/ui/product/route/{product_model}")
def ui_product_route(product_model: str) -> dict:
    return services.product_route_detail(product_model)


@router.get("/api/ui/product/report-index")
def ui_report_index(
    barcode: str | None = Query(default=None),
    step_no: str | None = Query(default=None),
) -> list[dict]:
    from ...repositories import report_details_store, report_route

    from ... import config, engine as eg
    from sqlalchemy import text
    from ...repositories.base import with_read_conn

    engines = []
    if step_no:
        with with_read_conn() as conn:
            row = conn.execute(
                text("SELECT step_name FROM steps WHERE step_no = :sn"), {"sn": step_no}
            ).fetchone()
        if row is not None:
            engines = [eg.get_report_engine(step_no, row[0])]
    else:
        for path in sorted(config.data_dir().glob("db_*.db")):
            parts = path.stem.split("_", 2)
            if len(parts) == 3:
                engines.append(eg.get_report_engine(parts[1], parts[2]))
        engines.append(eg.get_details_engine())

    rows = []
    for eng in engines:
        rows.extend(report_details_store.list_overview(barcode, eng))
    rows.sort(key=lambda r: r.get("id", 0), reverse=True)
    return rows


@router.get("/api/ui/product/report-details")
def ui_report_details(
    table: str = Query(min_length=3),
    step_no: str | None = Query(default=None),
) -> list[dict]:
    """按总览表给出的表名读取明细（只允许内部派生格式 SN_<safe>_<hash16>）。"""
    import re

    from ...repositories import report_details_store

    if not re.fullmatch(r"SN_[0-9A-Za-z_]{1,40}_[0-9a-f]{16}", table):
        return []
    from ... import config, engine as eg
    from sqlalchemy import text
    from ...repositories.base import with_read_conn

    engines = []
    if step_no:
        with with_read_conn() as conn:
            row = conn.execute(
                text("SELECT step_name FROM steps WHERE step_no = :sn"), {"sn": step_no}
            ).fetchone()
        if row is not None:
            engines = [eg.get_report_engine(step_no, row[0])]
    else:
        for path in sorted(config.data_dir().glob("db_*.db")):
            parts = path.stem.split("_", 2)
            if len(parts) == 3:
                engines.append(eg.get_report_engine(parts[1], parts[2]))
        engines.append(eg.get_details_engine())

    for eng in engines:
        try:
            rows = report_details_store.list_details_by_table(table, eng)
        except Exception:
            continue
        if rows:
            return rows
    return []


@router.get("/api/ui/product/flow-overview")
def ui_product_flow_overview(
    barcode: str | None = Query(default=None),
    componentcode: str | None = Query(default=None),
    device: str | None = Query(default=None),
    board_status: str | None = Query(default=None),
    current_step: str | None = Query(default=None),
) -> list[dict]:
    from ...repositories import product_flow_store

    return product_flow_store.list_overview(
        barcode=barcode, componentcode=componentcode, device=device,
        board_status=board_status, current_step=current_step,
    )


@router.get("/api/ui/product/flow-details")
def ui_product_flow_details(flow_table: str = Query(min_length=3)) -> list[dict]:
    from ...repositories import product_flow_store

    return product_flow_store.list_flow(flow_table)


@router.get("/api/ui/product/step-options")
def ui_step_options() -> list[dict]:
    from ...repositories import master_data_repo

    return master_data_repo.list_steps()
