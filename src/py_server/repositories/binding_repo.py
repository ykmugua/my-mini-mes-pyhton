"""程序绑定与拉取/状态日志的 SQL（唯一写 SQL 处）。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from .. import engine
from .base import Conn, dialect_insert, rows_to_dicts, with_read_conn, with_conn

pb = engine.program_bindings
pulls = engine.program_pull_logs
status_logs = engine.program_status_logs


def list_bindings(conn: Conn | None = None) -> list[dict]:
    if conn is None:
        with with_read_conn() as c:
            return list_bindings(c)
    stmt = select(pb).order_by(pb.c.device_id, pb.c.product)
    return rows_to_dicts(conn.execute(stmt).fetchall())


def try_binding(conn: Conn, device_id: str, product: str | None) -> Any | None:
    """按设备+产品查找绑定；product 为空且该设备只有一条绑定时返回该条。"""
    if product:
        stmt = select(pb).where(pb.c.device_id == device_id, pb.c.product == product)
    else:
        stmt = select(pb).where(pb.c.device_id == device_id).order_by(pb.c.product)
    rows = conn.execute(stmt).fetchall()
    if product:
        return rows[0] if rows else None
    return rows[0] if len(rows) == 1 else None


def binding_count(conn: Conn, device_id: str) -> int:
    from sqlalchemy import func

    stmt = select(func.count()).select_from(pb).where(pb.c.device_id == device_id)
    return int(conn.execute(stmt).fetchone()[0])


def binding_products(conn: Conn, device_id: str) -> list[str]:
    stmt = select(pb.c.product).where(pb.c.device_id == device_id).order_by(pb.c.product)
    return [str(row[0]) for row in conn.execute(stmt).fetchall()]


def upsert_binding(conn: Conn, row: dict, now: str) -> None:
    stmt = dialect_insert(pb).values(
        device_id=row["device_id"],
        product=row["product"],
        program_version=row["program_version"],
        download_url=row["download_url"],
        sha256=row["sha256"],
        updated_at=now,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["device_id", "product"],
        set_={
            "program_version": stmt.excluded.program_version,
            "download_url": stmt.excluded.download_url,
            "sha256": stmt.excluded.sha256,
            "updated_at": stmt.excluded.updated_at,
        },
    )
    conn.execute(stmt)


def replace_bindings(conn: Conn, cleaned: list[dict], now: str) -> None:
    """整体替换绑定关系（先 upsert，再删除不在清单内的记录）。"""
    from sqlalchemy import or_

    for row in cleaned:
        upsert_binding(conn, row, now)
    if cleaned:
        conditions = [
            (pb.c.device_id == r["device_id"]) & (pb.c.product == r["product"])
            for r in cleaned
        ]
        stmt = pb.delete().where(~or_(*conditions))
    else:
        stmt = pb.delete()
    conn.execute(stmt)


def mark_pulled(conn: Conn, binding_id: int, now: str) -> None:
    stmt = (
        pb.update()
        .where(pb.c.id == binding_id)
        .values(last_pull_at=now, updated_at=now)
    )
    conn.execute(stmt)


def insert_pull_log(conn: Conn, row: dict) -> None:
    conn.execute(pulls.insert().values(**row))


def update_reported_status(conn: Conn, binding_id: int, *, version, sha, reported_at, program_ok, now) -> None:
    stmt = (
        pb.update()
        .where(pb.c.id == binding_id)
        .values(
            reported_version=version,
            reported_sha256=sha,
            reported_at=reported_at,
            program_ok=program_ok,
            updated_at=now,
        )
    )
    conn.execute(stmt)


def insert_status_log(conn: Conn, row: dict) -> None:
    conn.execute(status_logs.insert().values(**row))


def program_drift(conn: Conn | None = None) -> list[dict]:
    from sqlalchemy import or_

    if conn is None:
        with with_read_conn() as c:
            return program_drift(c)
    stmt = (
        select(pb)
        .where(
            or_(
                pb.c.program_ok == 0,
                (pb.c.reported_version.is_not(None))
                & (pb.c.reported_version != pb.c.program_version),
                (pb.c.reported_sha256.is_not(None))
                & (func.lower(pb.c.reported_sha256) != func.lower(pb.c.sha256)),
            )
        )
        .order_by(pb.c.device_id, pb.c.product)
    )
    return rows_to_dicts(conn.execute(stmt).fetchall())


def list_pull_logs(conn: Conn | None = None, limit: int = 50) -> list[dict]:
    if conn is None:
        with with_read_conn() as c:
            return list_pull_logs(c, limit)
    stmt = select(pulls).order_by(pulls.c.id.desc()).limit(limit)
    return rows_to_dicts(conn.execute(stmt).fetchall())


def list_status_logs(conn: Conn | None = None, limit: int = 50) -> list[dict]:
    if conn is None:
        with with_read_conn() as c:
            return list_status_logs(c, limit)
    stmt = select(status_logs).order_by(status_logs.c.id.desc()).limit(limit)
    return rows_to_dicts(conn.execute(stmt).fetchall())