"""Pydantic 请求/响应模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, Field, field_validator


class ProgramStatusIn(BaseModel):
    """ProgramStatusIn 类。"""
    device_id: str = Field(min_length=1)
    product: str | None = None
    program_version: str | None = Field(
        default=None,
        validation_alias=AliasChoices("program_version", "version", "reported_version"),
    )
    sha256: str | None = Field(
        default=None,
        validation_alias=AliasChoices("sha256", "program_sha256", "reported_sha256"),
    )
    sha256_ok: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("sha256_ok", "checksum_ok", "verified"),
    )
    reported_at: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("reported_at", "timestamp", "loaded_at"),
    )


class TestResultIn(BaseModel):
    """TestResultIn 类。"""
    workpiece: str = Field(
        min_length=1,
        validation_alias=AliasChoices("workpiece", "workpiece_code", "workpiece_id"),
    )
    device_id: str = Field(min_length=1)
    test_item: str = Field(min_length=1)
    result: str
    measured_value: str | float | int | None = None
    program_version: str | None = None
    program_sha256: str | None = Field(
        default=None,
        validation_alias=AliasChoices("program_sha256", "sha256"),
    )
    product: str | None = None
    tested_at: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("tested_at", "timestamp", "ts"),
    )

    @field_validator("result")
    @classmethod
    def _normalize_result(cls, value: str) -> str:
        """执行 normalize_result。"""
        value = (value or "").strip().upper()
        if value not in ("PASS", "FAIL"):
            raise ValueError("result 只能是 PASS 或 FAIL")
        return value


class VariableWriteIn(BaseModel):
    """VariableWriteIn 类。"""
    value: Any = None
    device_id: str = Field(
        min_length=1,
        validation_alias=AliasChoices("device_id", "device", "writer"),
    )


class BindingsIn(BaseModel):
    """BindingsIn 类。"""
    rows: list[dict] = Field(default_factory=list)


class UpstreamRulesIn(BaseModel):
    """UpstreamRulesIn 类。"""
    rows: list[dict] = Field(default_factory=list)


class VariableCreateIn(BaseModel):
    """VariableCreateIn 类。"""
    name: str = Field(min_length=1)
    type: str = Field(min_length=1)
    value: Any = None


class UnlockIn(BaseModel):
    """UnlockIn 类。"""
    workpiece: str = Field(min_length=1)
    operator: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    target_step: str | None = None
    note: str | None = None
    confirmed: bool = False

class MasterDataIn(BaseModel):
    """MasterDataIn 类。"""
    rows: list[dict] = Field(default_factory=list)


class WorkbenchInboundIn(BaseModel):
    """WorkbenchInboundIn 类。"""
    product: str = Field(min_length=1)
    step_no: str = Field(min_length=1)
    traycode: str = Field(min_length=1)
    barcodes: list[str] = Field(default_factory=list)
    operator: str = Field(min_length=1)


class WorkbenchTrayUnbindIn(BaseModel):
    """WorkbenchTrayUnbindIn 类。"""
    traycode: str = Field(min_length=1)
    operator: str = Field(min_length=1)
    confirmed: bool = False


class VariableRenameIn(BaseModel):
    """VariableRenameIn 类。"""
    name: str = Field(min_length=1)


class VariableUpdateIn(BaseModel):
    """VariableUpdateIn 类。"""
    type: str | None = None
    value: Any = None
