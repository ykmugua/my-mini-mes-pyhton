"""MES 测试结果上传接口 V1.3 的请求/响应模型（字符串原样接收）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, ConfigDict


class TestDetailIn(BaseModel):
    """单条测试明细；所有字段均为字符串，服务端不解析。"""

    model_config = ConfigDict(populate_by_name=True)

    TestItem: str = Field(alias="TestItem")
    TestStep: str = Field(alias="TestStep")
    StandardValue: str = Field(alias="StandardValue")
    UpperValue: str = Field(alias="UpperValue")
    LowerValue: str = Field(alias="LowerValue")
    MeasureValue: str = Field(alias="MeasureValue")
    TestResult: str = Field(alias="TestResult")
    TestBeginTime: str = Field(alias="TestBeginTime")
    TestEndTime: str = Field(alias="TestEndTime")


class TestResultUploadIn(BaseModel):
    """整单上报：linecode/station/componentcode/barcode/..."""

    model_config = ConfigDict(populate_by_name=True)

    linecode: str = Field(min_length=1)
    station: str = Field(min_length=1)
    componentcode: str = Field(min_length=1)
    barcode: str = Field(min_length=1)
    programname: str = Field(min_length=1)
    programversion: str = Field(min_length=1)
    testexecutetime: str = Field(min_length=1)
    result: str = Field(min_length=1)
    testlongtime: str = Field(min_length=1)
    details: list[TestDetailIn] = Field(min_length=1)
    isfinalreport: str = Field(min_length=1)


class ApiEnvelope(BaseModel):
    """统一响应信封。"""

    success: bool
    message: str
    code: int
    result: dict[str, Any] | None = None
