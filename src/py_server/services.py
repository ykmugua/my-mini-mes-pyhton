"""业务服务层：页面与设备接口共用的业务规则。

设计要点
--------
* 所有函数自行获取/关闭 SQLite 连接，便于被 Streamlit 和 FastAPI 同时复用；
* 业务校验失败抛 ``ServiceError`` 子类，API 层统一转换为 4xx JSON；
* 工序锁规则（前道 PASS、FAIL 拦截、程序可信）全部集中在这里，页面与接口行为一致。
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

from . import config, db

# -----------------------------------------------------------------------------
# 异常
# -----------------------------------------------------------------------------
class ServiceError(Exception):
    """业务异常基类，API 层据此返回 4xx。"""

    status_code = 400


class ValidationError(ServiceError):
    status_code = 400


class NotFoundError(ServiceError):
    status_code = 404


class ConflictError(ServiceError):
    status_code = 409


# -----------------------------------------------------------------------------
# 连接工具
# -----------------------------------------------------------------------------
@contextmanager
def _read():
    conn = db.get_conn()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def _tx():
    conn = db.get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _clean_text(value: Any, field: str, *, max_len: int = 128) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValidationError(f"{field}不能为空")
    if len(text) > max_len:
        raise ValidationError(f"{field}长度不能超过 {max_len} 个字符")
    return text


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _clean_sha256(value: Any, field: str = "SHA256") -> str:
    text = "" if value is None else str(value).strip().lower()
    if not text:
        raise ValidationError(f"{field}不能为空")
    if not _SHA256_RE.match(text):
        raise ValidationError(f"{field} 应为 64 位十六进制字符串")
    return text


def _clean_url(value: Any) -> str:
    text = _clean_text(value, "下载 URL", max_len=512)
    if not (text.startswith("http://") or text.startswith("https://") or text.startswith("/")):
        raise ValidationError("下载 URL 需以 http://、https:// 或 / 开头")
    return text


def _try_binding(conn: sqlite3.Connection, device_id: str, product: str | None) -> sqlite3.Row | None:
    """按设备+产品查找绑定；product 为空且该设备只有一条绑定时返回该条。"""
    if product:
        return conn.execute(
            "SELECT * FROM program_bindings WHERE device_id = ? AND product = ?",
            (device_id, product),
        ).fetchone()
    rows = conn.execute(
        "SELECT * FROM program_bindings WHERE device_id = ? ORDER BY product", (device_id,)
    ).fetchall()
    return rows[0] if len(rows) == 1 else None


def _binding_count(conn: sqlite3.Connection, device_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM program_bindings WHERE device_id = ?", (device_id,)
    ).fetchone()
    return int(row["n"])


def _binding_or_404(conn: sqlite3.Connection, device_id: str, product: str | None) -> sqlite3.Row:
    binding = _try_binding(conn, device_id, product)
    if binding is None:
        if not product and _binding_count(conn, device_id) > 1:
            raise ValidationError(f"设备 {device_id} 绑定了多个产品，请指定 product")
        suffix = f"、产品 {product}" if product else ""
        raise NotFoundError(f"设备 {device_id}{suffix} 未配置程序绑定")
    return binding


def _resolve_product(
    conn: sqlite3.Connection,
    device_id: str,
    product: str | None,
    workpiece_product: str | None,
) -> str:
    """确定一次请求对应的产品型号。

    工件已记录产品时以工件为准（产品是工件的固有属性，不允许被单次请求改写）；
    仅当工件还没有产品记录时，才使用显式入参或设备的唯一绑定。
    """
    if workpiece_product:
        return str(workpiece_product).strip()
    if product:
        return str(product).strip()
    rows = conn.execute(
        "SELECT product FROM program_bindings WHERE device_id = ? ORDER BY product", (device_id,)
    ).fetchall()
    if len(rows) == 1:
        return str(rows[0]["product"])
    return ""


# -----------------------------------------------------------------------------
# 程序下发
# -----------------------------------------------------------------------------
def list_bindings() -> list[dict]:
    with _read() as conn:
        rows = conn.execute(
            "SELECT * FROM program_bindings ORDER BY device_id, product"
        ).fetchall()
        return db.rows_to_dicts(rows)


def replace_bindings(rows: Iterable[dict]) -> int:
    """用页面表格整体替换绑定关系（新增/修改/删除）。"""
    cleaned: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for index, raw in enumerate(rows, start=1):
        device_id = _clean_text(raw.get("device_id"), f"第 {index} 行设备标识")
        product = _clean_text(raw.get("product"), f"第 {index} 行产品型号")
        version = _clean_text(raw.get("program_version"), f"第 {index} 行程序版本", max_len=64)
        download_url = _clean_url(raw.get("download_url"))
        sha256 = _clean_sha256(raw.get("sha256"), f"第 {index} 行 SHA256")
        key = (device_id, product)
        if key in seen:
            raise ValidationError(f"第 {index} 行：设备 {device_id} + 产品 {product} 重复")
        seen.add(key)
        cleaned.append(
            {
                "device_id": device_id,
                "product": product,
                "program_version": version,
                "download_url": download_url,
                "sha256": sha256,
            }
        )

    now = db.utc_now_iso()
    with _tx() as conn:
        for row in cleaned:
            conn.execute(
                """
                INSERT INTO program_bindings
                    (device_id, product, program_version, download_url, sha256, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (device_id, product) DO UPDATE SET
                    program_version = excluded.program_version,
                    download_url = excluded.download_url,
                    sha256 = excluded.sha256,
                    updated_at = excluded.updated_at
                """,
                (
                    row["device_id"],
                    row["product"],
                    row["program_version"],
                    row["download_url"],
                    row["sha256"],
                    now,
                ),
            )
        if cleaned:
            placeholders = ",".join("?" for _ in cleaned)
            keys = [(row["device_id"], row["product"]) for row in cleaned]
            conditions = " OR ".join(["(device_id = ? AND product = ?)"] * len(keys))
            params = [value for pair in keys for value in pair]
            conn.execute(
                f"DELETE FROM program_bindings WHERE NOT ({conditions})", params
            )
        else:
            conn.execute("DELETE FROM program_bindings")
    return len(cleaned)


def upsert_binding(
    device_id: str,
    product: str,
    program_version: str,
    download_url: str,
    sha256: str,
) -> dict:
    device_id = _clean_text(device_id, "设备标识")
    product = _clean_text(product, "产品型号")
    program_version = _clean_text(program_version, "程序版本", max_len=64)
    download_url = _clean_url(download_url)
    sha256 = _clean_sha256(sha256)
    now = db.utc_now_iso()
    with _tx() as conn:
        conn.execute(
            """
            INSERT INTO program_bindings
                (device_id, product, program_version, download_url, sha256, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (device_id, product) DO UPDATE SET
                program_version = excluded.program_version,
                download_url = excluded.download_url,
                sha256 = excluded.sha256,
                updated_at = excluded.updated_at
            """,
            (device_id, product, program_version, download_url, sha256, now),
        )
        return dict(_binding_or_404(conn, device_id, product))


def publish_program_file(
    device_id: str,
    product: str,
    program_version: str,
    filename: str,
    content: bytes,
) -> dict:
    """保存上传的程序文件，自动计算 SHA256 并写入绑定。"""
    device_id = _clean_text(device_id, "设备标识")
    product = _clean_text(product, "产品型号")
    program_version = _clean_text(program_version, "程序版本", max_len=64)
    original = Path(filename).name if filename else "program.bin"
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", original) or "program.bin"
    prefix = re.sub(r"[^A-Za-z0-9._-]+", "_", f"{device_id}_{product}_{program_version}")
    stored_name = f"{prefix}_{safe_name}"
    target = config.program_dir() / stored_name
    target.write_bytes(content)
    sha256 = hashlib.sha256(content).hexdigest()
    url = f"{config.api_public_base()}/programs/{quote(stored_name)}"
    binding = upsert_binding(device_id, product, program_version, url, sha256)
    return {"binding": binding, "stored_path": str(target), "url": url, "sha256": sha256}


def record_program_pull(device_id: str, product: str | None) -> dict:
    """设备拉取程序元数据：返回绑定信息，同时记录拉取时间与拉取日志。"""
    device_id = _clean_text(device_id, "设备标识")
    now = db.utc_now_iso()
    with _tx() as conn:
        binding = _binding_or_404(conn, device_id, product)
        conn.execute(
            "UPDATE program_bindings SET last_pull_at = ?, updated_at = ? WHERE id = ?",
            (now, now, binding["id"]),
        )
        conn.execute(
            """
            INSERT INTO program_pull_logs
                (device_id, product, program_version, sha256, pulled_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (binding["device_id"], binding["product"], binding["program_version"], binding["sha256"], now),
        )
        data = dict(binding)
        data["last_pull_at"] = now
        data["pulled_at"] = now
        return data


def report_program_status(
    device_id: str,
    product: str | None,
    reported_version: str | None,
    reported_sha256: str | None,
    sha256_ok: bool | None = None,
) -> dict:
    """设备上报已加载版本与校验结果，返回该设备当前是否可生产。"""
    device_id = _clean_text(device_id, "设备标识")
    version = (reported_version or "").strip()
    sha = (reported_sha256 or "").strip().lower()
    now = db.utc_now_iso()
    with _tx() as conn:
        binding = _try_binding(conn, device_id, product)
        reasons: list[str] = []
        if binding is None:
            if _binding_count(conn, device_id) > 1 and not product:
                reasons.append(f"设备 {device_id} 绑定多个产品，请指定 product")
            else:
                reasons.append("设备未配置程序绑定")
            resolved_product = product or ""
            trusted = False
        else:
            resolved_product = binding["product"]
            if not version:
                reasons.append("未上报程序版本")
            elif version != binding["program_version"]:
                reasons.append(
                    f"上报版本 {version} 与绑定版本 {binding['program_version']} 不一致"
                )
            if not sha:
                reasons.append("未上报程序 SHA256")
            elif sha != binding["sha256"]:
                reasons.append("上报校验和与绑定校验和不一致")
            if sha256_ok is False:
                reasons.append("设备自检校验和不匹配")
            trusted = not reasons
            conn.execute(
                """
                UPDATE program_bindings
                SET reported_version = ?, reported_sha256 = ?, reported_at = ?,
                    program_ok = ?, updated_at = ?
                WHERE id = ?
                """,
                (version or None, sha or None, now, 1 if trusted else 0, now, binding["id"]),
            )
        reason = "；".join(reasons)
        conn.execute(
            """
            INSERT INTO program_status_logs
                (device_id, product, reported_version, reported_sha256, sha256_ok, trusted, reason, reported_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                device_id,
                resolved_product or None,
                version or None,
                sha or None,
                None if sha256_ok is None else (1 if sha256_ok else 0),
                1 if trusted else 0,
                reason or None,
                now,
            ),
        )
        return {
            "device_id": device_id,
            "product": resolved_product or None,
            "trusted": trusted,
            "can_produce": trusted,
            "reason": reason,
            "binding_version": binding["program_version"] if binding else None,
            "binding_sha256": binding["sha256"] if binding else None,
            "reported_version": version or None,
            "reported_sha256": sha or None,
            "checked_at": now,
        }


def program_drift() -> list[dict]:
    """返回版本漂移 / 校验不匹配 / 设备自检失败 / 上报信息不完整的绑定。"""
    with _read() as conn:
        rows = conn.execute(
            """
            SELECT * FROM program_bindings
            WHERE program_ok = 0
               OR (reported_version IS NOT NULL AND reported_version <> program_version)
               OR (reported_sha256 IS NOT NULL AND lower(reported_sha256) <> lower(sha256))
            ORDER BY device_id, product
            """
        ).fetchall()
        drifts = []
        for row in rows:
            item = dict(row)
            reasons = []
            if not item["reported_version"]:
                reasons.append("设备未上报程序版本")
            elif item["reported_version"] != item["program_version"]:
                reasons.append(f"版本 {item['reported_version']} ≠ 绑定 {item['program_version']}")
            if (
                item["reported_sha256"]
                and item["reported_sha256"].lower() != item["sha256"].lower()
            ):
                reasons.append("校验和不一致")
            if item["program_ok"] == 0:
                reasons.append("设备自检校验失败")
            item["drift_reason"] = "；".join(reasons) or "设备上报异常"
            drifts.append(item)
        return drifts


def list_program_pulls(limit: int = 50) -> list[dict]:
    with _read() as conn:
        rows = conn.execute(
            "SELECT * FROM program_pull_logs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return db.rows_to_dicts(rows)


def list_program_status_logs(limit: int = 50) -> list[dict]:
    with _read() as conn:
        rows = conn.execute(
            "SELECT * FROM program_status_logs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return db.rows_to_dicts(rows)


# -----------------------------------------------------------------------------
# 程序可信性 & 工序锁
# -----------------------------------------------------------------------------
def _evaluate_trust(
    conn: sqlite3.Connection,
    device_id: str,
    product: str | None,
    reported_version: str | None = None,
    reported_sha256: str | None = None,
) -> tuple[bool, str, sqlite3.Row | None]:
    """判断设备程序是否可信。

    * 入参带有版本/校验和时优先用入参（测试结果自带的版本信息）；
    * 否则使用设备最近一次 /api/program/status 上报的信息；
    * 未配置绑定、版本不一致、校验和不一致、设备自检失败都视为不可信。
    """
    if not product and _binding_count(conn, device_id) > 1:
        return False, f"设备 {device_id} 绑定多个产品，无法确定程序版本，请指定 product", None
    binding = _try_binding(conn, device_id, product)
    if binding is None:
        return False, f"设备 {device_id} 未配置程序绑定", None
    version = (reported_version or binding["reported_version"] or "").strip()
    sha = (reported_sha256 or binding["reported_sha256"] or "").strip().lower()
    reasons: list[str] = []
    if not version:
        reasons.append("设备未上报程序版本")
    elif version != binding["program_version"]:
        reasons.append(f"程序版本 {version} 与绑定版本 {binding['program_version']} 不一致")
    if not sha:
        reasons.append("设备未上报程序校验和")
    elif sha != binding["sha256"].lower():
        reasons.append("程序校验和与绑定不一致")
    if binding["program_ok"] == 0:
        reasons.append("设备最近一次程序校验失败")
    if reasons:
        return False, "；".join(reasons), binding
    return True, "", binding


def device_program_trust(device_id: str, product: str | None = None) -> dict:
    with _read() as conn:
        trusted, reason, binding = _evaluate_trust(conn, device_id, product)
        return {
            "device_id": device_id,
            "product": binding["product"] if binding else (product or None),
            "trusted": trusted,
            "reason": reason,
            "binding_version": binding["program_version"] if binding else None,
        }


def _get_workpiece(conn: sqlite3.Connection, workpiece: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM workpieces WHERE workpiece = ?", (workpiece,)
    ).fetchone()


def _workpiece_public(conn: sqlite3.Connection, workpiece: str) -> dict:
    row = _get_workpiece(conn, workpiece)
    if row is None:
        return {"workpiece": workpiece, "exists": False}
    data = dict(row)
    data["exists"] = True
    data["locked"] = bool(data.get("lock_reason"))
    return data


def _upstream_devices(conn: sqlite3.Connection, product: str, device_id: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT upstream_device_id FROM upstream_devices
        WHERE device_id = ? AND (product = ? OR product = '')
        ORDER BY upstream_device_id
        """,
        (device_id, product),
    ).fetchall()
    seen: set[str] = set()
    result: list[str] = []
    for row in rows:
        upstream = str(row["upstream_device_id"])
        if upstream not in seen:
            seen.add(upstream)
            result.append(upstream)
    return result


def _has_trusted_pass(
    conn: sqlite3.Connection, workpiece: str, device_id: str, product: str
) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM test_results
        WHERE workpiece = ? AND device_id = ? AND result = 'PASS' AND trusted = 1
          AND product = ?
        LIMIT 1
        """,
        (workpiece, device_id, product),
    ).fetchone()
    return row is not None


def _lock_workpiece(
    conn: sqlite3.Connection,
    workpiece: str,
    device_id: str | None,
    reason: str,
    now: str,
) -> None:
    conn.execute(
        """
        UPDATE workpieces
        SET lock_reason = ?, locked_at = ?, lock_device = ?, updated_at = ?
        WHERE workpiece = ? AND (lock_reason IS NULL OR lock_reason = '')
        """,
        (reason, now, device_id, now, workpiece),
    )


def report_test_result(
    *,
    workpiece: str,
    device_id: str,
    test_item: str,
    result: str,
    measured_value: Any = None,
    program_version: str | None = None,
    program_sha256: str | None = None,
    product: str | None = None,
    tested_at: Any = None,
) -> dict:
    """测试结果上报：幂等写入 + 自动锁定 + 返回工件状态。"""
    workpiece = _clean_text(workpiece, "工件码", max_len=128)
    device_id = _clean_text(device_id, "设备 ID")
    test_item = _clean_text(test_item, "测试项", max_len=128)
    result = (result or "").strip().upper()
    if result not in ("PASS", "FAIL"):
        raise ValidationError("判定结果只能是 PASS 或 FAIL")
    measured_text = "" if measured_value is None else str(measured_value)
    # 设备时间只能作为参考：未来时间会破坏“最新结果推进状态”的判定，先钳制到服务器时间。
    server_now = db.utc_now()
    parsed_tested_at = db.parse_ts(tested_at) or server_now
    max_future = server_now + timedelta(seconds=config.max_future_skew_seconds())
    tested_at_adjusted = parsed_tested_at > max_future
    if tested_at_adjusted:
        parsed_tested_at = server_now
    tested_at_iso = db.to_iso(parsed_tested_at)
    now = db.utc_now_iso()

    with _tx() as conn:
        existing_wp = _get_workpiece(conn, workpiece)
        requested_product = str(product).strip() if product else ""
        if (
            existing_wp
            and existing_wp["product"]
            and requested_product
            and requested_product != existing_wp["product"]
        ):
            raise ValidationError(
                f"工件 {workpiece} 已属于产品 {existing_wp['product']}，"
                f"不能以产品 {requested_product} 上报结果"
            )
        conn.execute(
            """
            INSERT OR IGNORE INTO workpieces
                (workpiece, product, status, created_at, updated_at)
            VALUES (?, ?, 'PENDING', ?, ?)
            """,
            (workpiece, product or None, now, now),
        )
        wp = _get_workpiece(conn, workpiece)
        resolved_product = _resolve_product(conn, device_id, product, wp["product"] if wp else None)
        if wp and not wp["product"] and resolved_product:
            conn.execute(
                "UPDATE workpieces SET product = ?, updated_at = ? WHERE workpiece = ?",
                (resolved_product, now, workpiece),
            )

        trusted, untrusted_reason, binding = _evaluate_trust(
            conn,
            device_id,
            resolved_product,
            reported_version=program_version,
            reported_sha256=program_sha256,
        )
        if binding and not resolved_product:
            resolved_product = binding["product"]

        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO test_results
                (workpiece, device_id, product, program_version, program_sha256, test_item,
                 measured_value, result, tested_at, reported_at, trusted, untrusted_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workpiece,
                device_id,
                resolved_product or None,
                (program_version or (binding["reported_version"] if binding else None)),
                (program_sha256 or (binding["reported_sha256"] if binding else None)),
                test_item,
                measured_text,
                result,
                tested_at_iso,
                now,
                1 if trusted else 0,
                untrusted_reason or None,
            ),
        )
        duplicate = cursor.rowcount == 0
        if duplicate:
            row = conn.execute(
                """
                SELECT * FROM test_results
                WHERE workpiece = ? AND device_id = ? AND test_item = ?
                """,
                (workpiece, device_id, test_item),
            ).fetchone()
            if row["result"] != result:
                raise ConflictError(
                    f"工件 {workpiece} 在设备 {device_id} 的测试项 {test_item} 已记录 "
                    f"{row['result']}，本次上报 {result} 与已有结果冲突。"
                    "同一测试项只记录一次；如需复测请使用新的测试项名称。"
                )
            return {
                "accepted": True,
                "duplicate": True,
                "stale": False,
                "id": row["id"],
                "workpiece": workpiece,
                "device_id": device_id,
                "test_item": test_item,
                "result": row["result"],
                "trusted": bool(row["trusted"]),
                "untrusted_reason": row["untrusted_reason"],
                "workpiece_status": _workpiece_public(conn, workpiece),
            }

        # 离线补传可能是更早的历史结果：只入库，不回滚/覆盖已推进的工件状态。
        # 比较时保留一小段时钟偏差容差，避免设备时间轻微偏慢导致真实的新 FAIL 被忽略。
        previous = conn.execute(
            "SELECT MAX(tested_at) AS latest FROM test_results WHERE workpiece = ? AND id <> ?",
            (workpiece, cursor.lastrowid),
        ).fetchone()
        latest_tested_at = previous["latest"]
        stale = False
        latest_dt = db.parse_ts(latest_tested_at)
        if latest_dt is not None:
            tolerance = timedelta(seconds=config.stale_tolerance_seconds())
            stale = parsed_tested_at < latest_dt - tolerance

        if stale:
            pass  # 历史结果仅保留记录，不改变工件状态、不锁定
        elif not trusted:
            _lock_workpiece(
                conn,
                workpiece,
                device_id,
                f"测试结果不可信（{untrusted_reason}）",
                now,
            )
        elif result == "FAIL":
            conn.execute(
                """
                UPDATE workpieces
                SET status = 'FAIL', current_device = ?, lock_reason = ?, locked_at = ?,
                    lock_device = ?, updated_at = ?
                WHERE workpiece = ?
                """,
                (
                    device_id,
                    f"测试项 {test_item} 判定 FAIL（设备 {device_id}）",
                    now,
                    device_id,
                    now,
                    workpiece,
                ),
            )
        else:  # PASS 且程序可信
            conn.execute(
                """
                UPDATE workpieces
                SET status = 'PASS', current_device = ?, updated_at = ?
                WHERE workpiece = ? AND (lock_reason IS NULL OR lock_reason = '')
                """,
                (device_id, now, workpiece),
            )
        return {
            "accepted": True,
            "duplicate": False,
            "stale": stale,
            "latest_tested_at": latest_tested_at,
            "tested_at_adjusted": tested_at_adjusted,
            "tested_at": tested_at_iso,
            "id": cursor.lastrowid,
            "workpiece": workpiece,
            "device_id": device_id,
            "test_item": test_item,
            "result": result,
            "trusted": trusted,
            "untrusted_reason": untrusted_reason or None,
            "workpiece_status": _workpiece_public(conn, workpiece),
        }


def interlock_check(
    workpiece: str, device_id: str | None = None, product: str | None = None
) -> dict:
    """查询工件能否在指定设备上操作，并给出不允许的原因。

    ``device_id`` 建议必传；未传时按工件最近一次所在设备判定，
    若工件还没有设备记录则无法判断前道/程序条件，直接拒绝。
    """
    workpiece = _clean_text(workpiece, "工件码", max_len=128)
    with _read() as conn:
        wp = _get_workpiece(conn, workpiece)
        device_id = (device_id or "").strip() or (
            (wp["current_device"] or "") if wp else ""
        )
        if not device_id:
            return {
                "workpiece": workpiece,
                "device_id": None,
                "product": product or None,
                "checked_at": db.utc_now_iso(),
                "status": wp["status"] if wp else "PENDING",
                "locked": bool(wp and wp["lock_reason"]),
                "lock_reason": wp["lock_reason"] if wp else None,
                "upstream_required": [],
                "allowed": False,
                "reason": "缺少 device_id，无法判定本设备的程序可信性与前道放行条件",
                "upstream_missing": [],
                "device_trusted": False,
                "manual_release": False,
            }
        resolved_product = _resolve_product(
            conn, device_id, product, wp["product"] if wp else None
        )
        requested_product = str(product).strip() if product else ""
        product_mismatch = (
            requested_product
            if (
                wp
                and wp["product"]
                and requested_product
                and requested_product != wp["product"]
            )
            else ""
        )
        trusted, trust_reason, binding = _evaluate_trust(conn, device_id, resolved_product)
        if binding and not resolved_product:
            resolved_product = binding["product"]
        upstreams = _upstream_devices(conn, resolved_product, device_id)
        base = {
            "workpiece": workpiece,
            "device_id": device_id,
            "product": resolved_product or None,
            "checked_at": db.utc_now_iso(),
            "status": wp["status"] if wp else "PENDING",
            "locked": bool(wp and wp["lock_reason"]),
            "lock_reason": wp["lock_reason"] if wp else None,
            "upstream_required": upstreams,
        }

        def deny(reason: str, missing: list[str] | None = None) -> dict:
            return {
                **base,
                "allowed": False,
                "reason": reason,
                "upstream_missing": missing or [],
                "device_trusted": trusted,
            }

        if product_mismatch:
            return deny(
                f"工件 {workpiece} 属于产品 {wp['product']}，"
                f"与请求产品 {product_mismatch} 不一致"
            )
        if not trusted:
            return deny(f"设备程序不可信：{trust_reason}")
        if wp and wp["lock_reason"]:
            return deny(wp["lock_reason"])
        if wp and wp["status"] == "FAIL":
            return deny("工件存在 FAIL 记录，已锁定")
        if wp and wp["manual_release_at"]:
            return {
                **base,
                "allowed": True,
                "reason": "人工解锁放行",
                "upstream_missing": [],
                "device_trusted": True,
                "manual_release": True,
            }
        missing = [
            upstream for upstream in upstreams if not _has_trusted_pass(conn, workpiece, upstream)
        ]
        if missing:
            return deny(
                "前道关键设备无 PASS 记录：" + "、".join(missing),
                missing,
            )
        return {
            **base,
            "allowed": True,
            "reason": "",
            "upstream_missing": [],
            "device_trusted": True,
            "manual_release": False,
        }


def list_locked_workpieces() -> list[dict]:
    with _read() as conn:
        rows = conn.execute(
            """
            SELECT * FROM workpieces
            WHERE lock_reason IS NOT NULL AND lock_reason <> ''
            ORDER BY locked_at DESC
            """
        ).fetchall()
        return db.rows_to_dicts(rows)


def unlock_workpiece(
    workpiece: str,
    operator: str,
    reason: str,
    confirmed: bool = False,
) -> dict:
    """人工解锁：必须填写原因并勾选确认，全部动作留痕。"""
    workpiece = _clean_text(workpiece, "工件码", max_len=128)
    operator = _clean_text(operator, "解锁人", max_len=64)
    reason = _clean_text(reason, "解锁原因", max_len=512)
    if not confirmed:
        raise ValidationError("必须勾选确认后才能解锁")
    now = db.utc_now_iso()
    with _tx() as conn:
        wp = _get_workpiece(conn, workpiece)
        if wp is None:
            raise NotFoundError(f"工件 {workpiece} 不存在")
        if not wp["lock_reason"]:
            raise ValidationError(f"工件 {workpiece} 当前未处于锁定状态")
        previous_reason = wp["lock_reason"]
        conn.execute(
            """
            INSERT INTO unlock_logs
                (workpiece, operator, reason, device_id, lock_reason, unlocked_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (workpiece, operator, reason, wp["current_device"], previous_reason, now),
        )
        conn.execute(
            """
            UPDATE workpieces
            SET status = 'PENDING', lock_reason = NULL, locked_at = NULL, lock_device = NULL,
                unlock_by = ?, unlock_reason = ?, unlocked_at = ?, manual_release_at = ?,
                updated_at = ?
            WHERE workpiece = ?
            """,
            (operator, reason, now, now, now, workpiece),
        )
        data = _workpiece_public(conn, workpiece)
        data["previous_lock_reason"] = previous_reason
        data["unlock_log"] = {
            "workpiece": workpiece,
            "operator": operator,
            "reason": reason,
            "unlocked_at": now,
        }
        return data


def list_unlock_logs(limit: int = 50) -> list[dict]:
    with _read() as conn:
        rows = conn.execute(
            "SELECT * FROM unlock_logs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return db.rows_to_dicts(rows)


def list_upstream_rules() -> list[dict]:
    with _read() as conn:
        rows = conn.execute(
            "SELECT * FROM upstream_devices ORDER BY device_id, upstream_device_id"
        ).fetchall()
        return db.rows_to_dicts(rows)


def replace_upstream_rules(rows: Iterable[dict]) -> int:
    """整体替换“前道关键设备”配置（可配置，不写死在代码里）。"""
    cleaned: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for index, raw in enumerate(rows, start=1):
        product = ("" if raw.get("product") is None else str(raw.get("product"))).strip()
        device_id = _clean_text(raw.get("device_id"), f"第 {index} 行设备标识")
        upstream = _clean_text(raw.get("upstream_device_id"), f"第 {index} 行前道设备")
        if device_id == upstream:
            raise ValidationError(f"第 {index} 行：前道设备不能是设备自身")
        key = (product, device_id, upstream)
        if key in seen:
            raise ValidationError(f"第 {index} 行：配置重复")
        seen.add(key)
        cleaned.append(
            {"product": product, "device_id": device_id, "upstream_device_id": upstream}
        )
    with _tx() as conn:
        conn.execute("DELETE FROM upstream_devices")
        conn.executemany(
            """
            INSERT INTO upstream_devices (product, device_id, upstream_device_id)
            VALUES (:product, :device_id, :upstream_device_id)
            """,
            cleaned,
        )
    return len(cleaned)


def list_devices() -> list[str]:
    """所有出现过的设备标识（用于看板筛选）。"""
    with _read() as conn:
        rows = conn.execute(
            """
            SELECT device_id FROM program_bindings
            UNION SELECT device_id FROM test_results
            UNION SELECT device_id FROM upstream_devices
            UNION SELECT upstream_device_id FROM upstream_devices
            ORDER BY 1
            """
        ).fetchall()
        return [str(row["device_id"]) for row in rows]


# -----------------------------------------------------------------------------
# 看板统计
# -----------------------------------------------------------------------------
def dashboard_snapshot(device_filter: str | None = None) -> dict:
    """今日看板数据：总体指标、按设备合格率、FAIL 分布、最新上报。

    “今日”按设备的测试时间 ``tested_at`` 统计（而不是服务器收到上报的时间），
    这样离线缓存补传的历史数据不会被误计入今天；合格率只统计可信数据，
    不可信数据单独计数并排除出合格率，FAIL 分布保留全部 FAIL 便于现场排查。
    """
    start, end = db.today_bounds_utc()
    device = (device_filter or "").strip() or None
    device_clause = " AND device_id = ?" if device else ""
    params: list[Any] = [start, end] + ([device] if device else [])

    with _read() as conn:
        totals = conn.execute(
            f"""
            SELECT COUNT(*) AS total,
                   COALESCE(SUM(CASE WHEN result = 'PASS' THEN 1 ELSE 0 END), 0) AS pass_count,
                   COALESCE(SUM(CASE WHEN result = 'FAIL' THEN 1 ELSE 0 END), 0) AS fail_count
            FROM test_results
            WHERE tested_at >= ? AND tested_at < ?{device_clause}
            """,
            params,
        ).fetchone()
        trusted = conn.execute(
            f"""
            SELECT COUNT(*) AS total,
                   COALESCE(SUM(CASE WHEN result = 'PASS' THEN 1 ELSE 0 END), 0) AS pass_count,
                   COALESCE(SUM(CASE WHEN result = 'FAIL' THEN 1 ELSE 0 END), 0) AS fail_count
            FROM test_results
            WHERE trusted = 1 AND tested_at >= ? AND tested_at < ?{device_clause}
            """,
            params,
        ).fetchone()
        untrusted = conn.execute(
            f"""
            SELECT COUNT(*) AS n FROM test_results
            WHERE trusted = 0 AND tested_at >= ? AND tested_at < ?{device_clause}
            """,
            params,
        ).fetchone()
        by_device = conn.execute(
            f"""
            SELECT device_id,
                   COUNT(*) AS total,
                   SUM(CASE WHEN result = 'PASS' THEN 1 ELSE 0 END) AS pass_count,
                   SUM(CASE WHEN result = 'FAIL' THEN 1 ELSE 0 END) AS fail_count
            FROM test_results
            WHERE trusted = 1 AND tested_at >= ? AND tested_at < ?{device_clause}
            GROUP BY device_id
            ORDER BY device_id
            """,
            params,
        ).fetchall()
        fail_by_item = conn.execute(
            f"""
            SELECT test_item AS label, COUNT(*) AS count
            FROM test_results
            WHERE result = 'FAIL' AND tested_at >= ? AND tested_at < ?{device_clause}
            GROUP BY test_item
            ORDER BY count DESC, label
            """,
            params,
        ).fetchall()
        fail_by_device = conn.execute(
            f"""
            SELECT device_id AS label, COUNT(*) AS count
            FROM test_results
            WHERE result = 'FAIL' AND tested_at >= ? AND tested_at < ?{device_clause}
            GROUP BY device_id
            ORDER BY count DESC, label
            """,
            params,
        ).fetchall()
        latest = conn.execute(
            f"""
            SELECT * FROM test_results
            WHERE tested_at >= ? AND tested_at < ?{device_clause}
            ORDER BY id DESC LIMIT 20
            """,
            params,
        ).fetchall()

    total = int(totals["total"])
    pass_count = int(totals["pass_count"])
    fail_count = int(totals["fail_count"])
    trusted_total = int(trusted["total"])
    trusted_pass = int(trusted["pass_count"])
    trusted_fail = int(trusted["fail_count"])
    tested = trusted_pass + trusted_fail
    by_device_rows: list[dict] = []
    for row in by_device:
        passed = int(row["pass_count"] or 0)
        failed = int(row["fail_count"] or 0)
        count = passed + failed
        by_device_rows.append(
            {
                "device_id": row["device_id"],
                "total": count,
                "pass": passed,
                "fail": failed,
                "yield": (passed / count) if count else None,
            }
        )
    tz = config.timezone()
    now_local = db.utc_now().astimezone(tz)
    return {
        "date": now_local.strftime("%Y-%m-%d"),
        "window": (start, end),
        "total": total,
        "pass": pass_count,
        "fail": fail_count,
        "trusted_total": trusted_total,
        "trusted_pass": trusted_pass,
        "trusted_fail": trusted_fail,
        "untrusted": int(untrusted["n"]),
        "yield": (trusted_pass / tested) if tested else None,
        "by_device": by_device_rows,
        "fail_by_item": [
            {"label": row["label"], "count": int(row["count"])} for row in fail_by_item
        ],
        "fail_by_device": [
            {"label": row["label"], "count": int(row["count"])} for row in fail_by_device
        ],
        "latest": db.rows_to_dicts(latest),
    }


# -----------------------------------------------------------------------------
# 开放性变量
# -----------------------------------------------------------------------------
VARIABLE_TYPES = ("int", "str", "bool")
# 变量名会出现在 /api/variable/{name} 路径里，限制为 URL 安全字符，
# 避免创建出设备无法寻址的变量名（如 a/b、a?b）。
_VARIABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,63}$")


def coerce_variable_value(type_name: str, value: Any) -> str:
    """按变量类型把外部输入转换成规范字符串（数据库存储形式）。"""
    type_name = (type_name or "").strip()
    if type_name not in VARIABLE_TYPES:
        raise ValidationError("变量类型只能是 int / str / bool")
    if type_name == "int":
        if isinstance(value, bool):
            raise ValidationError("int 类型变量不能使用布尔值")
        if isinstance(value, int):
            return str(value)
        text = "" if value is None else str(value).strip()
        if not text:
            raise ValidationError("int 类型变量需要提供整数值")
        try:
            return str(int(text, 10))
        except ValueError as exc:
            raise ValidationError(f"无法把 {text!r} 解析为整数") from exc
    if type_name == "bool":
        if isinstance(value, bool):
            return "true" if value else "false"
        text = "" if value is None else str(value).strip().lower()
        if text in ("true", "1", "yes", "y", "on"):
            return "true"
        if text in ("false", "0", "no", "n", "off"):
            return "false"
        raise ValidationError("bool 类型变量只接受 true/false")
    return "" if value is None else str(value)


def typed_variable_value(type_name: str, stored: str | None) -> str | int | bool | None:
    if stored is None:
        return None
    if type_name == "int":
        try:
            return int(stored)
        except (TypeError, ValueError):
            return stored
    if type_name == "bool":
        return str(stored).lower() == "true"
    return stored


def _variable_public(row: sqlite3.Row) -> dict:
    return {
        "name": row["name"],
        "type": row["type"],
        "value": typed_variable_value(row["type"], row["value"]),
        "raw_value": row["value"],
        "last_device": row["last_device"],
        "updated_at": row["updated_at"],
    }


def list_variables(prefix: str = "") -> list[dict]:
    prefix = (prefix or "").strip()
    with _read() as conn:
        if prefix:
            escaped = (
                prefix.replace("\\", r"\\").replace("%", r"\%").replace("_", r"\_") + "%"
            )
            rows = conn.execute(
                r"SELECT * FROM variables WHERE name LIKE ? ESCAPE '\' ORDER BY name",
                (escaped,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM variables ORDER BY name").fetchall()
        return [_variable_public(row) for row in rows]


def get_variable(name: str) -> dict:
    name = _clean_text(name, "变量名", max_len=64)
    with _read() as conn:
        row = conn.execute("SELECT * FROM variables WHERE name = ?", (name,)).fetchone()
        if row is None:
            raise NotFoundError(f"变量 {name} 不存在")
        return _variable_public(row)


def add_variable(name: str, type_name: str, value: Any = None) -> dict:
    name = "" if name is None else str(name).strip()
    if not name:
        raise ValidationError("变量名不能为空")
    if not _VARIABLE_NAME_RE.match(name):
        raise ValidationError(
            "变量名只能包含英文字母、数字、下划线、点和短横线，且以字母或下划线开头（长度 ≤ 64）"
        )
    stored = coerce_variable_value(type_name, value)
    now = db.utc_now_iso()
    with _tx() as conn:
        exists = conn.execute("SELECT 1 FROM variables WHERE name = ?", (name,)).fetchone()
        if exists:
            raise ConflictError(f"变量 {name} 已存在")
        conn.execute(
            """
            INSERT INTO variables (name, type, value, last_device, updated_at)
            VALUES (?, ?, ?, NULL, ?)
            """,
            (name, type_name, stored, now),
        )
        row = conn.execute("SELECT * FROM variables WHERE name = ?", (name,)).fetchone()
        return _variable_public(row)


def set_variable(name: str, value: Any, device_id: str) -> dict:
    name = _clean_text(name, "变量名", max_len=64)
    device_id = _clean_text(device_id, "写入设备", max_len=128)
    with _tx() as conn:
        row = conn.execute("SELECT * FROM variables WHERE name = ?", (name,)).fetchone()
        if row is None:
            raise NotFoundError(f"变量 {name} 不存在")
        stored = coerce_variable_value(row["type"], value)
        now = db.utc_now_iso()
        conn.execute(
            "UPDATE variables SET value = ?, last_device = ?, updated_at = ? WHERE name = ?",
            (stored, device_id, now, name),
        )
        row = conn.execute("SELECT * FROM variables WHERE name = ?", (name,)).fetchone()
        return _variable_public(row)
