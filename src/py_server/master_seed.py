"""主数据演示数据：从 app_pages 原型迁移而来，供 seed 初始化。"""

from __future__ import annotations

import json
from pathlib import Path

from .repositories import master_data_repo
from .repositories.base import with_conn

_DATA_FILE = Path(__file__).with_name("master_data.json")
_KEYS = (
    "steps",
    "lines",
    "devices",
    "trays",
    "programs",
    "program_versions",
    "program_components",
    "products",
    "product_routes",
    "product_step_devices",
)


def seed_master_data() -> None:
    """写入主数据演示数据（整体替换）。"""
    data = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
    with with_conn() as conn:
        master_data_repo.replace_steps(conn, data["steps"])
        master_data_repo.replace_lines(conn, data["lines"])
        master_data_repo.replace_devices(conn, data["devices"])
        master_data_repo.replace_trays(conn, data["trays"])
        master_data_repo.replace_programs(conn, data["programs"])
        master_data_repo.replace_program_versions(conn, data["program_versions"])
        master_data_repo.replace_program_components(conn, data["program_components"])
        master_data_repo.replace_products(conn, data["products"])
        master_data_repo.replace_product_routes(conn, data["product_routes"])
        master_data_repo.replace_product_step_devices(conn, data["product_step_devices"])