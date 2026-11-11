"""SQLite 数据层：连接管理、表结构、时间处理。

Streamlit 页面与 FastAPI 设备接口共用这一层（同一个数据库文件）。
SQLite 采用 WAL 模式，允许“一个写 + 多个读”，满足本工具的低并发场景。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import config

# -----------------------------------------------------------------------------
# 表结构
# -----------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS program_bindings (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id         TEXT NOT NULL,
    product           TEXT NOT NULL,
    program_version   TEXT NOT NULL,
    download_url      TEXT NOT NULL,
    sha256            TEXT NOT NULL,
    last_pull_at      TEXT,
    reported_version  TEXT,
    reported_sha256   TEXT,
    reported_at       TEXT,
    program_ok        INTEGER,
    updated_at        TEXT NOT NULL,
    UNIQUE (device_id, product)
);

CREATE TABLE IF NOT EXISTS program_pull_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id       TEXT NOT NULL,
    product         TEXT NOT NULL,
    program_version TEXT,
    sha256          TEXT,
    pulled_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pull_logs_time ON program_pull_logs (pulled_at);

CREATE TABLE IF NOT EXISTS program_status_logs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id         TEXT NOT NULL,
    product           TEXT,
    reported_version  TEXT,
    reported_sha256   TEXT,
    sha256_ok         INTEGER,
    trusted           INTEGER NOT NULL,
    reason            TEXT,
    reported_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_status_logs_time ON program_status_logs (reported_at);

CREATE TABLE IF NOT EXISTS workpieces (
    workpiece          TEXT PRIMARY KEY,
    product            TEXT,
    current_device     TEXT,
    status             TEXT NOT NULL DEFAULT 'PENDING',  -- PASS / FAIL / PENDING
    lock_reason        TEXT,
    locked_at          TEXT,
    lock_device        TEXT,
    unlock_by          TEXT,
    unlock_reason      TEXT,
    unlocked_at        TEXT,
    manual_release_at  TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_workpieces_locked ON workpieces (lock_reason, locked_at);

CREATE TABLE IF NOT EXISTS unlock_logs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    workpiece      TEXT NOT NULL,
    operator       TEXT NOT NULL,
    reason         TEXT NOT NULL,
    device_id      TEXT,
    lock_reason    TEXT,
    unlocked_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_unlock_logs_time ON unlock_logs (unlocked_at);

CREATE TABLE IF NOT EXISTS test_results (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    workpiece         TEXT NOT NULL,
    device_id         TEXT NOT NULL,
    product           TEXT,
    program_version   TEXT,
    program_sha256    TEXT,
    test_item         TEXT NOT NULL,
    measured_value    TEXT,
    result            TEXT NOT NULL CHECK (result IN ('PASS', 'FAIL')),
    tested_at         TEXT NOT NULL,
    reported_at       TEXT NOT NULL,
    trusted           INTEGER NOT NULL DEFAULT 1,
    untrusted_reason  TEXT,
    UNIQUE (workpiece, device_id, test_item)
);
CREATE INDEX IF NOT EXISTS idx_results_reported ON test_results (reported_at);
CREATE INDEX IF NOT EXISTS idx_results_device ON test_results (device_id, reported_at);
CREATE INDEX IF NOT EXISTS idx_results_workpiece ON test_results (workpiece);

CREATE TABLE IF NOT EXISTS variables (
    name        TEXT PRIMARY KEY,
    type        TEXT NOT NULL CHECK (type IN ('int', 'str', 'bool')),
    value       TEXT,
    last_device TEXT,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS upstream_devices (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    product            TEXT NOT NULL DEFAULT '',  -- 空字符串表示对所有产品生效
    device_id          TEXT NOT NULL,
    upstream_device_id TEXT NOT NULL,
    UNIQUE (product, device_id, upstream_device_id)
);

CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at TEXT NOT NULL
);
"""

_initialized_paths: set[str] = set()


def reset_for_tests() -> None:
    """测试中切换数据库文件时清空进程内的初始化缓存。"""
    _initialized_paths.clear()


def connect() -> sqlite3.Connection:
    """创建一个已执行 PRAGMA 的连接。调用方负责关闭。"""
    path = Path(config.db_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db(conn: sqlite3.Connection | None = None) -> None:
    """创建缺失的表和索引，可以重复执行。"""
    own = conn is None
    conn = conn or connect()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        if own:
            conn.close()


def get_conn() -> sqlite3.Connection:
    """获取连接，并保证当前数据库文件至少初始化过一次。"""
    path = str(config.db_path())
    conn = connect()
    if path not in _initialized_paths:
        init_db(conn)
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
    """解析设备时间戳，支持 datetime / ISO 字符串 / Unix 秒或毫秒。

    不带时区的时间按业务时区（默认 Asia/Shanghai）解释。
    """
    if value is None or value == "":
        return default
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        number = float(value)
        if number > 1e12:  # 毫秒时间戳
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
            # 兼容 "2026-11-11 08:30:00" 这类空格分隔写法
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
