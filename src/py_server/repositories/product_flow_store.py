"""产品流转库：ProductFlow.db（总览表 + 每产品一张流转表）。

状态枚举：normal / lock / final
时间格式：YYYY-MM-DD HH:MM:SS（业务时区）
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from sqlalchemy import text

from .. import config, engine as eg


def flow_table_name(barcode: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z_]", "_", barcode)[:40]
    digest = hashlib.sha256(barcode.encode("utf-8")).hexdigest()[:16]
    return f"F_{safe}_{digest}"


def _eng():
    return eg.get_product_flow_engine()


def normalize_time(value: str) -> str:
    """统一转成 YYYY-MM-DD HH:MM:SS（业务时区）。"""
    if not value:
        return datetime.now(config.timezone()).strftime("%Y-%m-%d %H:%M:%S")
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(config.timezone()).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return str(value)


def _columns(conn, table: str) -> list[str]:
    return [row[1] for row in conn.execute(text(f"PRAGMA table_info(\"{table}\")")).fetchall()]


def ensure_overview_table() -> None:
    with _eng().begin() as conn:
        cols = _columns(conn, "product_overview") if conn.execute(text(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='product_overview'"
        )).scalar() else []
        if not cols:
            conn.execute(text("""
                CREATE TABLE product_overview (
                    id INTEGER PRIMARY KEY,
                    barcode TEXT NOT NULL,
                    componentcode TEXT NOT NULL,
                    traycode TEXT NOT NULL DEFAULT '',
                    board_status TEXT NOT NULL,
                    current_step TEXT NOT NULL,
                    last_report_device TEXT NOT NULL,
                    last_report_note TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL,
                    flow_table TEXT NOT NULL
                )
            """))
        else:
            if "current_device" in cols and "last_report_device" not in cols:
                conn.execute(text("ALTER TABLE product_overview RENAME COLUMN current_device TO last_report_device"))
            if "traycode" not in cols:
                conn.execute(text("ALTER TABLE product_overview ADD COLUMN traycode TEXT NOT NULL DEFAULT ''"))
            if "last_report_note" not in cols:
                conn.execute(text("ALTER TABLE product_overview ADD COLUMN last_report_note TEXT NOT NULL DEFAULT ''"))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_product_overview_barcode ON product_overview(barcode)"
        ))


def ensure_flow_table(barcode: str) -> str:
    table = flow_table_name(barcode)
    with _eng().begin() as conn:
        exists = conn.execute(text(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name=:t"
        ), {"t": table}).scalar()
        cols = _columns(conn, table) if exists else []
        if not cols:
            conn.execute(text(f"""
                CREATE TABLE "{table}" (
                    id INTEGER PRIMARY KEY,
                    board_status TEXT NOT NULL,
                    step_no TEXT NOT NULL,
                    next_step TEXT NOT NULL,
                    line_id TEXT NOT NULL,
                    device TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    changed_at TEXT NOT NULL
                )
            """))
        elif "note" not in cols:
            conn.execute(text(f"ALTER TABLE \"{table}\" ADD COLUMN note TEXT NOT NULL DEFAULT ''"))
    return table


def upsert_flow(
    *,
    barcode: str,
    componentcode: str,
    traycode: str | None = None,
    board_status: str,
    step_no: str,
    next_step: str,
    line_id: str,
    device: str,
    note: str = "",
    changed_at: str,
) -> None:
    """写一行流转记录，并更新总览表当前状态。"""
    ensure_overview_table()
    table = ensure_flow_table(barcode)
    ts = normalize_time(changed_at)
    with _eng().begin() as conn:
        conn.execute(text(f"""
            INSERT INTO "{table}"
            (board_status, step_no, next_step, line_id, device, note, changed_at)
            VALUES (:board_status, :step_no, :next_step, :line_id, :device, :note, :changed_at)
        """), {
            "board_status": board_status,
            "step_no": str(step_no),
            "next_step": str(next_step or ""),
            "line_id": str(line_id or ""),
            "device": str(device or ""),
            "note": str(note or ""),
            "changed_at": ts,
        })
        existing = conn.execute(
            text("SELECT id FROM product_overview WHERE barcode = :bc"), {"bc": barcode}
        ).fetchone()
        if existing is None:
            conn.execute(text("""
                INSERT INTO product_overview
                (barcode, componentcode, traycode, board_status, current_step, last_report_device,
                 last_report_note, updated_at, flow_table)
                VALUES (:bc, :cc, :tc, :bs, :step, :dev, :note, :ts, :ft)
            """), {
                "bc": barcode, "cc": componentcode or "", "tc": traycode or "", "bs": board_status,
                "step": str(step_no), "dev": device or "", "note": str(note or ""),
                "ts": ts, "ft": table,
            })
        else:
            if traycode is None:
                conn.execute(text("""
                    UPDATE product_overview
                    SET componentcode=:cc, board_status=:bs, current_step=:step,
                        last_report_device=:dev, last_report_note=:note,
                        updated_at=:ts, flow_table=:ft
                    WHERE barcode=:bc
                """), {
                    "bc": barcode, "cc": componentcode or "", "bs": board_status,
                    "step": str(step_no), "dev": device or "", "note": str(note or ""),
                    "ts": ts, "ft": table,
                })
            else:
                conn.execute(text("""
                    UPDATE product_overview
                    SET componentcode=:cc, traycode=:tc, board_status=:bs, current_step=:step,
                        last_report_device=:dev, last_report_note=:note,
                        updated_at=:ts, flow_table=:ft
                    WHERE barcode=:bc
                """), {
                    "bc": barcode, "cc": componentcode or "", "tc": traycode or "",
                    "bs": board_status, "step": str(step_no), "dev": device or "",
                    "note": str(note or ""), "ts": ts, "ft": table,
                })


def list_overview(
    barcode: str | None = None,
    componentcode: str | None = None,
    traycode: str | None = None,
    device: str | None = None,
    board_status: str | None = None,
    current_step: str | None = None,
) -> list[dict]:
    ensure_overview_table()
    conds = []
    params = {}
    if barcode:
        conds.append("barcode LIKE :bc")
        params["bc"] = f"%{barcode}%"
    if componentcode:
        conds.append("componentcode = :cc")
        params["cc"] = componentcode
    if traycode:
        conds.append("traycode = :tc")
        params["tc"] = traycode
    if device:
        conds.append("last_report_device = :dev")
        params["dev"] = device
    if board_status:
        conds.append("board_status = :bs")
        params["bs"] = board_status
    if current_step:
        conds.append("current_step = :step")
        params["step"] = str(current_step)
    sql = "SELECT * FROM product_overview"
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY id DESC"
    with _eng().connect() as conn:
        result = conn.execute(text(sql), params)
        return [dict(row._mapping) for row in result.fetchall()]


def list_flow(flow_table: str) -> list[dict]:
    if not re.fullmatch(r"F_[0-9A-Za-z_]{1,40}_[0-9a-f]{16}", flow_table):
        return []
    with _eng().connect() as conn:
        result = conn.execute(text(f'SELECT * FROM "{flow_table}" ORDER BY id ASC'))
        return [dict(row._mapping) for row in result.fetchall()]


def reset_all() -> None:
    with _eng().begin() as conn:
        rows = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
        for row in rows:
            name = row[0]
            if name.startswith("F_"):
                conn.execute(text(f'DROP TABLE IF EXISTS "{name}"'))
        conn.execute(text("DROP TABLE IF EXISTS product_overview"))
        seq = conn.execute(text(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'"
        )).scalar()
        if seq:
            conn.execute(text("DROP TABLE IF EXISTS sqlite_sequence"))
