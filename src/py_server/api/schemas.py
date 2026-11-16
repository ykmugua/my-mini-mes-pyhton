"""Pydantic 请求/响应模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, Field, field_validator


class ProgramStatusIn(BaseModel):
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
        value = (value or "").strip().upper()
        if value not in ("PASS", "FAIL"):
            raise ValueError("result 只能是 PASS 或 FAIL")
        return value


class VariableWriteIn(BaseModel):
    value: Any = None
    device_id: str = Field(
        min_length=1,
        validation_alias=AliasChoices("device_id", "device", "writer"),
    )


class BindingsIn(BaseModel):
    rows: list[dict] = Field(default_factory=list)


class UpstreamRulesIn(BaseModel):
    rows: list[dict] = Field(default_factory=list)


class VariableCreateIn(BaseModel):
    name: str = Field(min_length=1)
    type: str = Field(min_length=1)
    value: Any = None


class UnlockIn(BaseModel):
    workpiece: str = Field(min_length=1)
    operator: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    confirmed: bool = False

class MasterDataIn(BaseModel):
    rows: list[dict] = Field(default_factory=list)
