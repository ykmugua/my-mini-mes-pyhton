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
    status: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    limit: int = Query(default=200),
) -> list[dict]:
    return services.query_workpieces(
        product=product, workpiece=workpiece, status=status,
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