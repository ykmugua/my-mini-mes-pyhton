"""集中配置。

所有配置都支持环境变量覆盖，方便内网部署；默认值面向“开箱即用”的本地演示。
"""

from __future__ import annotations

import os
import socket
from pathlib import Path
from zoneinfo import ZoneInfo

#: 项目根目录（即 py-server 目录）
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _env_path(name: str, default: Path) -> Path:
    raw = os.environ.get(name, "").strip()
    return Path(raw).expanduser().resolve() if raw else default


def data_dir() -> Path:
    """数据目录，存放 SQLite 数据库、程序文件和缓存。"""
    path = _env_path("MES_DATA_DIR", PROJECT_ROOT / "data")
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return _env_path("MES_DB_PATH", data_dir() / "mes.db")


def program_dir() -> Path:
    """程序文件静态目录，由接口服务挂载到 /programs。"""
    path = _env_path("MES_PROGRAM_DIR", data_dir() / "programs")
    path.mkdir(parents=True, exist_ok=True)
    return path


def timezone() -> ZoneInfo:
    """业务时区，用于“今日”统计与时间展示。"""
    return ZoneInfo(os.environ.get("MES_TZ", "Asia/Shanghai"))


def api_port() -> int:
    return int(os.environ.get("MES_API_PORT", "8000"))


def local_ip() -> str:
    """探测本机内网 IP，用于拼出设备可访问的程序下载地址。"""
    probe = os.environ.get("MES_PROBE_HOST", "192.0.2.1")
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect((probe, 9))  # UDP connect 不会真正发包，只取出口网卡地址
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def api_public_base() -> str:
    """设备访问接口服务的基础地址（不含结尾斜杠）。"""
    explicit = os.environ.get("MES_API_PUBLIC_BASE", "").strip()
    if explicit:
        return explicit.rstrip("/")
    return f"http://{local_ip()}:{api_port()}"


def max_future_skew_seconds() -> int:
    """设备时间戳允许超前服务器时间的秒数，超出则钳制到服务器当前时间。"""
    return int(os.environ.get("MES_MAX_FUTURE_SKEW_SECONDS", "300"))


def stale_tolerance_seconds() -> int:
    """判断“历史补传”时允许的时钟偏差容差（秒）。"""
    return int(os.environ.get("MES_STALE_TOLERANCE_SECONDS", "300"))
