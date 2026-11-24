"""时间工具与数据库初始化入口。

表结构定义与连接管理在 engine.py；本模块保留被各层广泛使用的 UTC 时间工具和
init_db/reset_for_tests 入口。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from . import config, engine

def reset_for_tests() -> None:
    """测试中切换数据库文件时清空缓存（db 与 engine 两层）。"""
    engine.reset_for_tests()


def init_db() -> None:
    """创建缺失的表（只做 create_all）。"""
    engine.init_schema()


# -----------------------------------------------------------------------------
# 时间工具：数据库统一存 UTC ISO 字符串；展示时转业务时区
# -----------------------------------------------------------------------------
def utc_now() -> datetime:
    """执行 utc_now。"""
    return datetime.now(timezone.utc)


def to_iso(dt: datetime) -> str:
    """转为带时区的 UTC ISO 字符串（秒精度，便于字符串排序）。"""
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def utc_now_iso() -> str:
    """执行 utc_now_iso。"""
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
    """规范化ts。"""
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


