"""产品进站校验接口请求/响应模型。"""

from __future__ import annotations


from pydantic import BaseModel, Field


class WorkpieceCheckInIn(BaseModel):
    """设备扫描产品后的只读进站资格校验请求。"""

    barcode: str = Field(min_length=1)
    station: str = Field(min_length=1)
    fixturecode: str = Field(min_length=1)
    traycode: str = Field(min_length=1)


class WorkpieceCheckInData(BaseModel):
    """校验通过时返回的工艺信息。"""

    processcode: str
    stepon: str


class WorkpieceCheckInOut(BaseModel):
    """业务信封；业务校验不通过仍使用 HTTP 200。"""

    success: bool
    code: str
    message: str
    data: WorkpieceCheckInData | None = None
