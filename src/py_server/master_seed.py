"""主数据演示数据：从 app_pages 原型迁移而来，供 seed 初始化。"""

from __future__ import annotations

import json
from pathlib import Path

from .repositories import master_data_repo
from .repositories.base import with_conn

_DATA_FILE = Path(__file__).with_name("master_data.json")
_KEYS = (
    "steps", "devices", "trays", "programs", "program_versions",
    "products", "processes", "process_routes", "process_step_resources",
)


def seed_master_data() -> None:
    """写入主数据演示数据（整体替换）。"""
    data = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
    with with_conn() as conn:
        master_data_repo.replace_steps(conn, data["steps"])
        master_data_repo.replace_devices(conn, data["devices"])
        master_data_repo.replace_trays(conn, data["trays"])
        master_data_repo.replace_programs(conn, data["programs"])
        master_data_repo.replace_program_versions(conn, data["program_versions"])
        master_data_repo.replace_products(conn, data["products"])
        master_data_repo.replace_processes(conn, data["processes"])
        master_data_repo.replace_process_routes(conn, data["process_routes"])
        master_data_repo.replace_process_step_resources(conn, data["process_step_resources"])
