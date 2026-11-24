"""兼容 re-export：实际路由位于 device/program.py。"""

from .device.program import router

__all__ = ["router"]
