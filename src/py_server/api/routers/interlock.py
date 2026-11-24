"""兼容 re-export：实际路由位于 common/interlock.py。"""

from .common.interlock import router

__all__ = ["router"]
