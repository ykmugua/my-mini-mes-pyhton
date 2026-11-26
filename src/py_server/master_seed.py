"""主数据演示数据：从 app_pages 原型迁移而来，供 seed 初始化。"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .repositories import master_data_repo
from .repositories.base import with_conn

def _data_file() -> Path:
    """返回当前进程使用的主数据种子文件。"""
    override = os.getenv("MES_MASTER_SEED_FILE")
    if override:
        return Path(override)
    return Path(__file__).with_name("master_data.json")
_KEYS = (
    "steps", "devices", "trays", "needle_beds", "programs", "program_versions",
    "products", "processes", "process_routes", "process_step_resources",
)


def seed_master_data() -> None:
    """写入主数据演示数据（整体替换）。"""
    data = json.loads(_data_file().read_text(encoding="utf-8"))
    with with_conn() as conn:
        master_data_repo.replace_steps(conn, data["steps"])
        master_data_repo.replace_devices(conn, data["devices"])
        master_data_repo.replace_trays(conn, data["trays"])
        master_data_repo.replace_needle_beds(conn, data.get("needle_beds", []))
        master_data_repo.replace_programs(conn, data["programs"])
        master_data_repo.replace_program_versions(conn, data["program_versions"])
        master_data_repo.replace_products(conn, data["products"])
        master_data_repo.replace_processes(conn, data["processes"])
        master_data_repo.replace_process_routes(conn, data["process_routes"])
        master_data_repo.replace_process_step_resources(conn, data["process_step_resources"])
