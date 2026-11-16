"""upstream_devices 的 SQL（唯一写 SQL 处）。"""

from __future__ import annotations

from sqlalchemy import delete, select

from .. import engine
from .base import Conn, rows_to_dicts, with_read_conn

u = engine.upstream_devices


def list_rules(conn: Conn | None = None) -> list[dict]:
    if conn is None:
        with with_read_conn() as c:
            return list_rules(c)
    stmt = select(u).order_by(u.c.device_id, u.c.upstream_device_id)
    return rows_to_dicts(conn.execute(stmt).fetchall())


def replace_rules(conn: Conn, cleaned: list[dict]) -> None:
    conn.execute(delete(u))
    if cleaned:
        conn.execute(u.insert(), cleaned)


def upstream_devices(conn: Conn, product: str, device_id: str) -> list[str]:
    stmt = (
        select(u.c.upstream_device_id)
        .where(u.c.device_id == device_id, (u.c.product == product) | (u.c.product == ""))
        .order_by(u.c.upstream_device_id)
    )
    seen: set[str] = set()
    result: list[str] = []
    for row in conn.execute(stmt).fetchall():
        upstream = str(row[0])
        if upstream not in seen:
            seen.add(upstream)
            result.append(upstream)
    return result


def has_trusted_pass(conn: Conn, *, workpiece: str, device_id: str, product: str) -> bool:
    from sqlalchemy import func

    tr = engine.test_results
    stmt = (
        select(func.count())
        .select_from(tr)
        .where(
            tr.c.workpiece == workpiece,
            tr.c.device_id == device_id,
            tr.c.result == "PASS",
            tr.c.trusted == 1,
            tr.c.product == product,
        )
        .limit(1)
    )
    return int(conn.execute(stmt).fetchone()[0]) > 0


def list_devices(conn: Conn | None = None) -> list[str]:
    if conn is None:
        with with_read_conn() as c:
            return list_devices(c)
    from sqlalchemy import union_all

    q1 = select(engine.program_bindings.c.device_id)
    q2 = select(engine.test_results.c.device_id)
    q3 = select(u.c.device_id)
    q4 = select(u.c.upstream_device_id)
    from sqlalchemy import text
    stmt = union_all(q1, q2, q3, q4).order_by(text('1'))
    return [str(row[0]) for row in conn.execute(stmt).fetchall()]