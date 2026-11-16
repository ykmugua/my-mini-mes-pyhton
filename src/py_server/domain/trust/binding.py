"""Binding 值对象：程序的绑定基线。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Binding:
    device_id: str
    product: str
    program_version: str
    download_url: str
    sha256: str
    reported_version: str | None = None
    reported_sha256: str | None = None
    program_ok: int | bool | None = None

    @classmethod
    def from_row(cls, row) -> "Binding":
        data = dict(row)
        return cls(
            device_id=data["device_id"],
            product=data["product"],
            program_version=data["program_version"],
            download_url=data["download_url"],
            sha256=data["sha256"],
            reported_version=data.get("reported_version"),
            reported_sha256=data.get("reported_sha256"),
            program_ok=data.get("program_ok"),
        )

    @property
    def self_check_failed(self) -> bool:
        return self.program_ok == 0