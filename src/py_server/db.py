"""兼容层：时间工具与旧的 db 接口。

表结构定义与连接管理已迁移到 engine.py（SQLAlchemy Engine）。
这里保留 db.* 的 API 供 seed/旧测试使用；init_db() 现在调用 engine.init_schema()。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from . import config, engine

# 兼容旧代码可能直接引用 db.SCHEMA / db._initialized_paths
_initialized_paths: set[str] = set()


def reset_for_tests() -> None:
    """测试中切换数据库文件时清空缓存（db 与 engine 两层）。"""
    _initialized_paths.clear()
    engine.reset_for_tests()


def connect() -> sqlite3.Connection:
    """保留旧接口：原始 sqlite3 连接（带 PRAGMA）。"""
    path = config.db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db(conn: sqlite3.Connection | None = None) -> None:
    """创建缺失的表（只做 create_all）。"""
    engine.init_schema()
    if conn is not None:
        conn.commit()


def get_conn() -> sqlite3.Connection:
    """保留旧接口供 services/seed 使用。"""
    path = str(config.db_path())
    conn = connect()
    if path not in _initialized_paths:
        init_db()
        _initialized_paths.add(path)
    return conn


# -----------------------------------------------------------------------------
# 时间工具：数据库统一存 UTC ISO 字符串；展示时转业务时区
# -----------------------------------------------------------------------------
def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(dt: datetime) -> str:
    """转为带时区的 UTC ISO 字符串（秒精度，便于字符串排序）。"""
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def utc_now_iso() -> str:
    return to_iso(utc_now())


def parse_ts(value: Any, *, default: datetime | None = None) -> datetime | None:
    """解析设备时间戳，支持 datetime / ISO 字符串 / Unix 秒或毫秒。"""
    if value is None or value == "":
        return default
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        number = float(value)
        if number > 1e12:
            number /= 1000
        dt = datetime.fromtimestamp(number, tz=timezone.utc)
    else:
        text = str(value).strip()
        if not text:
            return default
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            dt = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=config.timezone())
    return dt.astimezone(timezone.utc)


def normalize_ts(value: Any) -> str:
    parsed = parse_ts(value)
    return to_iso(parsed) if parsed else utc_now_iso()


def to_local_display(value: Any, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """把数据库里的 UTC 时间转成本地时间字符串；空值返回 '-'。"""
    parsed = parse_ts(value)
    if parsed is None:
        return "-"
    return parsed.astimezone(config.timezone()).strftime(fmt)


def today_bounds_utc(now: datetime | None = None) -> tuple[str, str]:
    """返回业务时区“今天”的 UTC 起止 ISO 字符串（左闭右开）。"""
    tz = config.timezone()
    local_now = (now or utc_now()).astimezone(tz)
    start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    return to_iso(start_local), to_iso(end_local)


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict]:
    return [dict(row) for row in rows]