"""业务服务层（兼容入口）。

所有 SQL 已迁移到 repositories/；可信判定与锁判定迁移到 domain/；
三个多步用例的事务编排迁移到 application/。本模块保留：
* 输入校验与清洗（保持原有错误文案）；
* 对外 API（tests/seed/router 仍可调用）；
* 单表简单 CRUD 的薄封装。
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from datetime import timedelta
from typing import Any, Iterable

from . import config, db
from .application import report_program_status as _report_program_status_uc
from .application import report_test_result as _report_test_result_uc
from .application import unlock_workpiece as _unlock_workpiece_uc
from .domain import ConflictError as DomainConflictError
from .domain import DomainError, InvariantViolation
from .domain.interlock.policy import InterlockDecision, InterlockPolicy, InterlockReason
from .domain.trust.binding import Binding
from .domain.trust.policy import ProgramTrustPolicy
from .domain.workpiece.model import Workpiece
from .repositories import (
    binding_repo,
    dashboard_repo,
    log_repo,
    program_files,
    upstream_repo,
    variable_repo,
    workpiece_repo,
)
from .repositories.base import Conn, with_conn as _with_conn, with_read_conn as _with_read


# -----------------------------------------------------------------------------
# 异常：ServiceError 继承 DomainError，保证 FastAPI 的异常处理器仍然生效
# -----------------------------------------------------------------------------
class ServiceError(DomainError):
    """业务异常基类，API 层据此返回 4xx。"""

    status_code = 400


class ValidationError(ServiceError):
    status_code = 400


class NotFoundError(ServiceError):
    status_code = 404


class ConflictError(ServiceError):
    status_code = 409


# -----------------------------------------------------------------------------
# 连接工具（兼容 seed/测试直接引用 services._tx / services._read）
# -----------------------------------------------------------------------------
@contextmanager
def _read():
    with _with_read() as conn:
        yield conn


@contextmanager
def _tx():
    with _with_conn() as conn:
        yield conn


# -----------------------------------------------------------------------------
# 输入清洗
# -----------------------------------------------------------------------------
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


def _try_binding(conn: Conn, device_id: str, product: str | None):
    return binding_repo.try_binding(conn, device_id, product)


def _binding_count(conn: Conn, device_id: str) -> int:
    return binding_repo.binding_count(conn, device_id)


def _binding_or_404(conn: Conn, device_id: str, product: str | None):
    binding = _try_binding(conn, device_id, product)
    if binding is None:
        if not product and _binding_count(conn, device_id) > 1:
            raise ValidationError(f"设备 {device_id} 绑定了多个产品，请指定 product")
        suffix = f"、产品 {product}" if product else ""
        raise NotFoundError(f"设备 {device_id}{suffix} 未配置程序绑定")
    return binding


def _resolve_product(conn: Conn, device_id: str, product: str | None, workpiece_product: str | None) -> str:
    if workpiece_product:
        return str(workpiece_product).strip()
    if product:
        return str(product).strip()
    products = binding_repo.binding_products(conn, device_id)
    return products[0] if len(products) == 1 else ""


# -----------------------------------------------------------------------------
# 程序下发
# -----------------------------------------------------------------------------
def list_bindings() -> list[dict]:
    return binding_repo.list_bindings()


def replace_bindings(rows: Iterable[dict]) -> int:
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
    with _tx() as conn:
        binding_repo.replace_bindings(conn, cleaned, db.utc_now_iso())
    return len(cleaned)


def upsert_binding(device_id, product, program_version, download_url, sha256) -> dict:
    device_id = _clean_text(device_id, "设备标识")
    product = _clean_text(product, "产品型号")
    program_version = _clean_text(program_version, "程序版本", max_len=64)
    download_url = _clean_url(download_url)
    sha256 = _clean_sha256(sha256)
    now = db.utc_now_iso()
    with _tx() as conn:
        binding_repo.upsert_binding(
            conn,
            {
                "device_id": device_id,
                "product": product,
                "program_version": program_version,
                "download_url": download_url,
                "sha256": sha256,
            },
            now,
        )
    with _read() as conn:
        return dict(_binding_or_404(conn, device_id, product))


def publish_program_file(device_id, product, program_version, filename, content) -> dict:
    device_id = _clean_text(device_id, "设备标识")
    product = _clean_text(product, "产品型号")
    program_version = _clean_text(program_version, "程序版本", max_len=64)
    saved = program_files.save_program_file(
        device_id=device_id,
        product=product,
        program_version=program_version,
        filename=filename,
        content=content,
    )
    binding = upsert_binding(device_id, product, program_version, saved["url"], saved["sha256"])
    return {"binding": binding, "stored_path": saved["stored_path"], "url": saved["url"], "sha256": saved["sha256"]}


def record_program_pull(device_id: str, product: str | None) -> dict:
    device_id = _clean_text(device_id, "设备标识")
    now = db.utc_now_iso()
    with _tx() as conn:
        binding = _binding_or_404(conn, device_id, product)
        binding_repo.mark_pulled(conn, binding["id"], now)
        binding_repo.insert_pull_log(
            conn,
            {
                "device_id": binding["device_id"],
                "product": binding["product"],
                "program_version": binding["program_version"],
                "sha256": binding["sha256"],
                "pulled_at": now,
            },
        )
        data = dict(binding)
        data["last_pull_at"] = now
        data["pulled_at"] = now
        return data


def report_program_status(device_id, product, reported_version, reported_sha256, sha256_ok=None) -> dict:
    device_id = _clean_text(device_id, "设备标识")
    version = (reported_version or "").strip()
    sha = (reported_sha256 or "").strip().lower()
    now = db.utc_now_iso()
    with _read() as conn:
        binding = _try_binding(conn, device_id, product)
        count = _binding_count(conn, device_id)
    reasons: list[str] = []
    if binding is None:
        if count > 1 and not product:
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
            reasons.append(f"上报版本 {version} 与绑定版本 {binding['program_version']} 不一致")
        if not sha:
            reasons.append("未上报程序 SHA256")
        elif sha != binding["sha256"]:
            reasons.append("上报校验和与绑定校验和不一致")
        if sha256_ok is False:
            reasons.append("设备自检校验和不匹配")
        trusted = not reasons
    return _report_program_status_uc.execute(
        device_id=device_id,
        product=product,
        reported_version=reported_version,
        reported_sha256=reported_sha256,
        sha256_ok=sha256_ok,
        binding=binding,
        binding_count=count,
        reasons=reasons,
        trusted=trusted,
        resolved_product=resolved_product,
        version=version,
        sha=sha,
        now=now,
    )


def program_drift() -> list[dict]:
    rows = binding_repo.program_drift()
    drifts: list[dict] = []
    for row in rows:
        item = dict(row)
        reasons: list[str] = []
        if not item["reported_version"]:
            reasons.append("设备未上报程序版本")
        elif item["reported_version"] != item["program_version"]:
            reasons.append(f"版本 {item['reported_version']} ≠ 绑定 {item['program_version']}")
        if item["reported_sha256"] and item["reported_sha256"].lower() != item["sha256"].lower():
            reasons.append("校验和不一致")
        if item["program_ok"] == 0:
            reasons.append("设备自检校验失败")
        item["drift_reason"] = "；".join(reasons) or "设备上报异常"
        drifts.append(item)
    return drifts


def list_program_pulls(limit: int = 50) -> list[dict]:
    return binding_repo.list_pull_logs(limit=limit)


def list_program_status_logs(limit: int = 50) -> list[dict]:
    return binding_repo.list_status_logs(limit=limit)


# -----------------------------------------------------------------------------
# 程序可信性 & 工序锁
# -----------------------------------------------------------------------------
def _evaluate_trust(conn: Conn, device_id: str, product: str | None, reported_version=None, reported_sha256=None):
    """兼容旧签名：内部委托 application 的领域策略实现。"""
    return _report_test_result_uc.evaluate_trust(
        conn,
        device_id=device_id,
        product=product,
        reported_version=reported_version,
        reported_sha256=reported_sha256,
    )


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


def _get_workpiece(conn: Conn, workpiece: str):
    return workpiece_repo.get_workpiece(conn, workpiece)


def _workpiece_public(conn: Conn, workpiece: str) -> dict:
    return workpiece_repo.public_workpiece(conn, workpiece)


def _upstream_devices(conn: Conn, product: str, device_id: str) -> list[str]:
    return upstream_repo.upstream_devices(conn, product, device_id)


def _has_trusted_pass(conn: Conn, workpiece: str, device_id: str, product: str) -> bool:
    return upstream_repo.has_trusted_pass(
        conn, workpiece=workpiece, device_id=device_id, product=product
    )


def _lock_workpiece(conn: Conn, workpiece, device_id, reason, now) -> None:
    workpiece_repo.lock_workpiece(
        conn, workpiece=workpiece, device_id=device_id, reason=reason, now=now
    )


def report_test_result(*, workpiece, device_id, test_item, result, measured_value=None,
                       program_version=None, program_sha256=None, product=None, tested_at=None) -> dict:
    workpiece = _clean_text(workpiece, "工件码", max_len=128)
    device_id = _clean_text(device_id, "设备 ID")
    test_item = _clean_text(test_item, "测试项", max_len=128)
    result = (result or "").strip().upper()
    if result not in ("PASS", "FAIL"):
        raise ValidationError("判定结果只能是 PASS 或 FAIL")
    measured_text = "" if measured_value is None else str(measured_value)
    server_now = db.utc_now()
    parsed_tested_at = db.parse_ts(tested_at) or server_now
    max_future = server_now + timedelta(seconds=config.max_future_skew_seconds())
    tested_at_adjusted = parsed_tested_at > max_future
    if tested_at_adjusted:
        parsed_tested_at = server_now
    tested_at_iso = db.to_iso(parsed_tested_at)
    now = db.utc_now_iso()

    try:
        return _report_test_result_uc.execute(
            workpiece=workpiece,
            device_id=device_id,
            test_item=test_item,
            result=result,
            measured_text=measured_text,
            tested_at_iso=tested_at_iso,
            now=now,
            parsed_tested_at=parsed_tested_at,
            tested_at_adjusted=tested_at_adjusted,
            product=product,
            program_version=program_version,
            program_sha256=program_sha256,
            ValidationError=ValidationError,
            ConflictError=ConflictError,
        )
    except DomainConflictError as exc:
        raise ConflictError(str(exc)) from exc
    except InvariantViolation as exc:
        raise ValidationError(str(exc)) from exc


def interlock_check(workpiece: str, device_id: str | None = None, product: str | None = None) -> dict:
    workpiece = _clean_text(workpiece, "工件码", max_len=128)
    with _read() as conn:
        wp_row = _get_workpiece(conn, workpiece)
        wp = Workpiece.from_row(wp_row) if wp_row else None
        device_id = (device_id or "").strip() or ((wp.current_device or "") if wp else "")
        resolved_product = _resolve_product(conn, device_id, product, wp_row["product"] if wp_row else None)
        requested_product = str(product).strip() if product else ""
        product_mismatch = (
            f"工件 {workpiece} 属于产品 {wp_row['product']}，与请求产品 {requested_product} 不一致"
            if wp_row and wp_row["product"] and requested_product and requested_product != wp_row["product"]
            else ""
        )
        trusted, trust_reason, binding = _evaluate_trust(conn, device_id, resolved_product or None)
        if binding and not resolved_product:
            resolved_product = binding["product"]
        upstreams = _upstream_devices(conn, resolved_product, device_id)
        trusted_pass = tuple(
            up for up in upstreams if _has_trusted_pass(conn, workpiece, up, resolved_product)
        )
        from .domain.trust.verdict import TrustReason, TrustVerdict

        trust_verdict = TrustVerdict(trusted, TrustReason.OK if trusted else TrustReason.NO_REPORT)

        decision = InterlockPolicy.evaluate(
            workpiece=wp,
            device_id=device_id or None,
            product=resolved_product or None,
            trust=trust_verdict,
            upstreams=tuple(upstreams),
            trusted_pass_upstreams=trusted_pass,
            trust_detail=trust_reason,
            product_mismatch=product_mismatch,
        )
        base = {
            "workpiece": workpiece,
            "device_id": device_id or None,
            "product": resolved_product or None,
            "checked_at": db.utc_now_iso(),
            "status": wp_row["status"] if wp_row else "PENDING",
            "locked": bool(wp and wp.locked),
            "lock_reason": wp_row["lock_reason"] if wp_row else None,
            "upstream_required": upstreams,
        }
        result = {
            **base,
            "allowed": decision.allowed,
            "reason": decision.detail,
            "upstream_missing": list(decision.upstream_missing),
            "device_trusted": trusted,
            "manual_release": decision.manual_release,
        }
        # 文案兜底：保持旧接口对 allowed=True 的空 reason
        if decision.reason is InterlockReason.OK:
            result["reason"] = ""
        return result


def list_locked_workpieces() -> list[dict]:
    return workpiece_repo.list_locked()


def unlock_workpiece(workpiece, operator, reason, confirmed=False) -> dict:
    workpiece = _clean_text(workpiece, "工件码", max_len=128)
    operator = _clean_text(operator, "解锁人", max_len=64)
    reason = _clean_text(reason, "解锁原因", max_len=512)
    if not confirmed:
        raise ValidationError("必须勾选确认后才能解锁")
    now = db.utc_now_iso()
    with _read() as conn:
        wp_row = _get_workpiece(conn, workpiece)
        if wp_row is None:
            raise NotFoundError(f"工件 {workpiece} 不存在")
    try:
        return _unlock_workpiece_uc.execute(
            wp_row=wp_row, operator=operator, reason=reason, confirmed=confirmed, now=now
        )
    except InvariantViolation as exc:
        raise ValidationError(str(exc)) from exc


def list_unlock_logs(limit: int = 50) -> list[dict]:
    return log_repo.list_unlock_logs(limit=limit)


def list_upstream_rules() -> list[dict]:
    return upstream_repo.list_rules()


def replace_upstream_rules(rows: Iterable[dict]) -> int:
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
        cleaned.append({"product": product, "device_id": device_id, "upstream_device_id": upstream})
    with _tx() as conn:
        upstream_repo.replace_rules(conn, cleaned)
    return len(cleaned)


def list_devices() -> list[str]:
    return upstream_repo.list_devices()


# -----------------------------------------------------------------------------
# 看板统计
# -----------------------------------------------------------------------------
def dashboard_snapshot(device_filter: str | None = None) -> dict:
    start, end = db.today_bounds_utc()
    device = (device_filter or "").strip() or None
    snap = dashboard_repo.snapshot(None, start=start, end=end, device=device)
    totals = snap["totals"]
    trusted = snap["trusted"]
    total = int(totals["total"])
    pass_count = int(totals["pass_count"])
    fail_count = int(totals["fail_count"])
    trusted_total = int(trusted["total"])
    trusted_pass = int(trusted["pass_count"])
    trusted_fail = int(trusted["fail_count"])
    tested = trusted_pass + trusted_fail
    by_device_rows: list[dict] = []
    for row in snap["by_device"]:
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
        "window": snap["window"],
        "total": total,
        "pass": pass_count,
        "fail": fail_count,
        "trusted_total": trusted_total,
        "trusted_pass": trusted_pass,
        "trusted_fail": trusted_fail,
        "untrusted": int(snap["untrusted"]),
        "yield": (trusted_pass / tested) if tested else None,
        "by_device": by_device_rows,
        "fail_by_item": [
            {"label": row["label"], "count": int(row["count"])} for row in snap["fail_by_item"]
        ],
        "fail_by_device": [
            {"label": row["label"], "count": int(row["count"])} for row in snap["fail_by_device"]
        ],
        "latest": snap["latest"],
    }


# -----------------------------------------------------------------------------
# 开放性变量
# -----------------------------------------------------------------------------
VARIABLE_TYPES = ("int", "float", "str", "bool")
_VARIABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,63}$")


def coerce_variable_value(type_name: str, value: Any) -> str:
    type_name = (type_name or "").strip()
    if type_name not in VARIABLE_TYPES:
        raise ValidationError("变量类型只能是 int / float / str / bool")
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
    if type_name == "float":
        if isinstance(value, bool):
            raise ValidationError("float 类型变量不能使用布尔值")
        text = "" if value is None else str(value).strip()
        if not text:
            raise ValidationError("float 类型变量需要提供数值")
        try:
            number = float(text)
        except ValueError as exc:
            raise ValidationError(f"无法把 {text!r} 解析为浮点数") from exc
        return repr(number)
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
    if type_name == "float":
        try:
            return float(stored)
        except (TypeError, ValueError):
            return stored
    if type_name == "bool":
        return str(stored).lower() == "true"
    return stored


def _variable_public(row) -> dict:
    return {
        "name": row["name"],
        "type": row["type"],
        "value": typed_variable_value(row["type"], row["value"]),
        "raw_value": row["value"],
        "last_device": row["last_device"],
        "updated_at": row["updated_at"],
    }


def list_variables(prefix: str = "") -> list[dict]:
    return [_variable_public(row) for row in variable_repo.list_variables(prefix=prefix)]


def get_variable(name: str, device_id: str | None = None) -> dict:
    name = _clean_text(name, "变量名", max_len=64)
    device_id = (device_id or "").strip()
    with _tx() as conn:
        row = variable_repo.get_variable_row(conn, name)
        if row is None:
            raise NotFoundError(f"变量 {name} 不存在")
        result = _variable_public(row)
        if device_id:
            variable_repo.insert_log(
                conn, name=name, action="READ", device_id=device_id,
                value=result["value"], now=db.utc_now_iso(),
            )
        return result


def add_variable(name: str, type_name: str, value: Any = None) -> dict:
    name = _validate_variable_name(name)
    stored = coerce_variable_value(type_name, value)
    now = db.utc_now_iso()
    with _tx() as conn:
        if variable_repo.exists(conn, name):
            raise ConflictError(f"变量 {name} 已存在")
        variable_repo.insert_variable(conn, name=name, type_name=type_name, stored=stored, now=now)
        row = variable_repo.get_variable_row(conn, name)
        return _variable_public(row)


def set_variable(name: str, value: Any, device_id: str) -> dict:
    name = _clean_text(name, "变量名", max_len=64)
    device_id = _clean_text(device_id, "写入设备", max_len=128)
    with _tx() as conn:
        row = variable_repo.get_variable_row(conn, name)
        if row is None:
            raise NotFoundError(f"变量 {name} 不存在")
        stored = coerce_variable_value(row["type"], value)
        now = db.utc_now_iso()
        variable_repo.update_variable(conn, name=name, stored=stored, device_id=device_id, now=now)
        variable_repo.insert_log(
            conn, name=name, action="WRITE", device_id=device_id,
            value=stored, now=now,
        )
        row = variable_repo.get_variable_row(conn, name)
        return _variable_public(row)


def _validate_variable_name(name: str) -> str:
    name = "" if name is None else str(name).strip()
    if not name:
        raise ValidationError("变量名不能为空")
    if not _VARIABLE_NAME_RE.match(name):
        raise ValidationError("变量名只能包含英文字母、数字、下划线、点和短横线，且以字母或下划线开头（长度 ≤ 64）")
    return name


def delete_variable(name: str) -> dict:
    name = _clean_text(name, "变量名", max_len=64)
    with _tx() as conn:
        if not variable_repo.exists(conn, name):
            raise NotFoundError(f"变量 {name} 不存在")
        variable_repo.delete_variable(conn, name)
    return {"name": name, "deleted": True}


def rename_variable(old_name: str, new_name: str) -> dict:
    old_name = _clean_text(old_name, "原变量名", max_len=64)
    new_name = _validate_variable_name(new_name)
    if old_name == new_name:
        with _read() as conn:
            row = variable_repo.get_variable_row(conn, old_name)
            if row is None:
                raise NotFoundError(f"变量 {old_name} 不存在")
            return _variable_public(row)
    with _tx() as conn:
        if not variable_repo.exists(conn, old_name):
            raise NotFoundError(f"变量 {old_name} 不存在")
        if variable_repo.exists(conn, new_name):
            raise ConflictError(f"变量 {new_name} 已存在")
        variable_repo.rename_variable(conn, old_name, new_name)
        row = variable_repo.get_variable_row(conn, new_name)
        return _variable_public(row)


def update_variable_def(name: str, *, type_name: str | None, value: Any) -> dict:
    """编辑变量定义：可改类型与初始值（value=None 表示保持当前值）。"""
    name = _clean_text(name, "变量名", max_len=64)
    with _tx() as conn:
        row = variable_repo.get_variable_row(conn, name)
        if row is None:
            raise NotFoundError(f"变量 {name} 不存在")
        resolved_type = type_name or row["type"]
        if value is None:
            stored = row["value"]
        else:
            stored = coerce_variable_value(resolved_type, value)
        now = db.utc_now_iso()
        variable_repo.update_variable_def(conn, name=name, type_name=resolved_type, stored=stored, now=now)
        row = variable_repo.get_variable_row(conn, name)
        return _variable_public(row)


# -----------------------------------------------------------------------------
# 三层变量树（展示/编辑辅助；不改变底层扁平存储与设备 API）
# -----------------------------------------------------------------------------
def split_variable_name(name: str) -> tuple[str, str, str]:
    """把点分变量名拆成最多三段：第一层.第二层.第三层。

    不足三段时右侧补空串，保持兼容现有扁平变量（line_mode）与两段变量（line_2.ready-x）。
    超过三段时把第三段及之后合并为第三段，保证最多三层。
    """
    parts = str(name or "").split(".")
    if len(parts) > 3:
        parts = parts[:2] + [".".join(parts[2:])]
    parts += [""] * (3 - len(parts))
    return parts[0], parts[1], parts[2]


def variables_tree(variables: list[dict]) -> dict:
    """把扁平变量列表解析为最多三层的树：{"A": {"B": {"C": value}}}。"""
    tree: dict = {}
    for item in variables:
        first, second, third = split_variable_name(item["name"])
        path = [part for part in (first, second, third) if part]
        if not path:
            continue
        node = tree
        for part in path[:-1]:
            child = node.get(part)
            if not isinstance(child, dict):
                child = {}
                node[part] = child
            node = child
        node[path[-1]] = item["value"]
    return tree


def variables_tree_from_api(prefix: str = "") -> dict:
    """供 UI 树形接口调用：读取变量并组装成三层树。"""
    return variables_tree(list_variables(prefix))



def list_variable_logs(*, action: str | None = None, limit: int = 30) -> list[dict]:
    return variable_repo.list_logs(action=action, limit=limit)
