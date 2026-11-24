"""兼容 re-export：实际路由位于 ui/product_query.py。"""

from .ui.product_query import router

__all__ = ["router"]
