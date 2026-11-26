"""工位操作台请求模型补充。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class WorkpieceDownlineIn(BaseModel):
    """无载具工件下线请求。"""
    barcode: str = Field(min_length=1)
    operator: str = Field(min_length=1)
    confirmed: bool = False
