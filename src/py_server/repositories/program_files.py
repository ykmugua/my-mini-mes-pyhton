"""程序文件读写 + SHA256（非 SQL 的仓库能力）。"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from urllib.parse import quote

from .. import config


def save_program_file(
    *, device_id: str, product: str, program_version: str, filename: str, content: bytes
) -> dict:
    """保存program_file。"""
    original = Path(filename).name if filename else "program.bin"
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", original) or "program.bin"
    prefix = re.sub(r"[^A-Za-z0-9._-]+", "_", f"{device_id}_{product}_{program_version}")
    stored_name = f"{prefix}_{safe_name}"
    target = config.program_dir() / stored_name
    target.write_bytes(content)
    sha256 = hashlib.sha256(content).hexdigest()
    url = f"{config.api_public_base()}/programs/{quote(stored_name)}"
    return {"stored_name": stored_name, "stored_path": str(target), "url": url, "sha256": sha256}


def resolve_download(filename: str) -> Path | None:
    """解析download。"""
    root = config.program_dir().resolve()
    target = (root / Path(filename).name).resolve()
    if target.parent != root or not target.is_file():
        return None
    return target