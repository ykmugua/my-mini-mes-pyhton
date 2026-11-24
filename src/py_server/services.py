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
from .application import station_workbench as _station_workbench_uc
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
    master_data_repo,
    program_files,
    product_flow_store,
    station_repo,
    upstream_repo,
    variable_repo,
    product_query_repo,
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
    """ValidationError 类。"""
    status_code = 400


class NotFoundError(ServiceError):
    """NotFoundError 类。"""
    status_code = 404


class ConflictError(ServiceError):
    """ConflictError 类。"""
    status_code = 409


# -----------------------------------------------------------------------------
# 连接工具：services 内部统一使用 with_conn/with_read_conn
# -----------------------------------------------------------------------------
@contextmanager
def _read():
    """执行 read。"""
    with _with_read() as conn:
        yield conn


@contextmanager
def _tx():
    """执行 tx。"""
    with _with_conn() as conn:
        yield conn


# -----------------------------------------------------------------------------
# 输入清洗
# -----------------------------------------------------------------------------
def _clean_text(value: Any, field: str, *, max_len: int = 128) -> str:
    """执行 clean_text。"""
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValidationError(f"{field}不能为空")
    if len(text) > max_len:
        raise ValidationError(f"{field}长度不能超过 {max_len} 个字符")
    return text


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _clean_sha256(value: Any, field: str = "SHA256") -> str:
    """执行 clean_sha256。"""
    text = "" if value is None else str(value).strip().lower()
    if not text:
        raise ValidationError(f"{field}不能为空")
    if not _SHA256_RE.match(text):
        raise ValidationError(f"{field} 应为 64 位十六进制字符串")
    return text


def _clean_url(value: Any) -> str:
    """执行 clean_url。"""
    text = _clean_text(value, "下载 URL", max_len=512)
    if not (text.startswith("http://") or text.startswith("https://") or text.startswith("/")):
        raise ValidationError("下载 URL 需以 http://、https:// 或 / 开头")
    return text


def _try_binding(conn: Conn, device_id: str, product: str | None):
    """执行 try_binding。"""
    return binding_repo.try_binding(conn, device_id, product)


def _binding_count(conn: Conn, device_id: str) -> int:
    """执行 binding_count。"""
    return binding_repo.binding_count(conn, device_id)


def _binding_or_404(conn: Conn, device_id: str, product: str | None):
    """执行 binding_or_404。"""
    binding = _try_binding(conn, device_id, product)
    if binding is None:
        if not product and _binding_count(conn, device_id) > 1:
            raise ValidationError(f"设备 {device_id} 绑定了多个产品，请指定 product")
        suffix = f"、产品 {product}" if product else ""
        raise NotFoundError(f"设备 {device_id}{suffix} 未配置程序绑定")
    return binding


def _resolve_product(conn: Conn, device_id: str, product: str | None, workpiece_product: str | None) -> str:
    """执行 resolve_product。"""
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
    """列出bindings。"""
    return binding_repo.list_bindings()


def replace_bindings(rows: Iterable[dict]) -> int:
    """替换bindings。"""
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
    """执行 upsert_binding。"""
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
    """执行 publish_program_file。"""
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
    """记录program_pull。"""
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
    """上报program_status。"""
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
    """执行 program_drift。"""
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
    """列出program_pulls。"""
    return binding_repo.list_pull_logs(limit=limit)


def list_program_status_logs(limit: int = 50) -> list[dict]:
    """列出program_status_logs。"""
    return binding_repo.list_status_logs(limit=limit)


# -----------------------------------------------------------------------------
# 程序可信性 & 工序锁
# -----------------------------------------------------------------------------
def _evaluate_trust(conn: Conn, device_id: str, product: str | None, reported_version=None, reported_sha256=None):
    """委托 application 的领域策略实现可信性判定。"""
    return _report_test_result_uc.evaluate_trust(
        conn,
        device_id=device_id,
        product=product,
        reported_version=reported_version,
        reported_sha256=reported_sha256,
    )


def device_program_trust(device_id: str, product: str | None = None) -> dict:
    """执行 device_program_trust。"""
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
    """执行 get_workpiece。"""
    return workpiece_repo.get_workpiece(conn, workpiece)


def _workpiece_public(conn: Conn, workpiece: str) -> dict:
    """执行 workpiece_public。"""
    return workpiece_repo.public_workpiece(conn, workpiece)


def _upstream_devices(conn: Conn, product: str, device_id: str) -> list[str]:
    """执行 upstream_devices。"""
    return upstream_repo.upstream_devices(conn, product, device_id)


def _has_trusted_pass(conn: Conn, workpiece: str, device_id: str, product: str) -> bool:
    """执行 has_trusted_pass。"""
    return upstream_repo.has_trusted_pass(
        conn, workpiece=workpiece, device_id=device_id, product=product
    )


def _lock_workpiece(conn: Conn, workpiece, device_id, reason, now) -> None:
    """执行 lock_workpiece。"""
    workpiece_repo.lock_workpiece(
        conn, workpiece=workpiece, device_id=device_id, reason=reason, now=now
    )


def report_test_result(*, workpiece, device_id, test_item, result, measured_value=None,
                       program_version=None, program_sha256=None, product=None, tested_at=None) -> dict:
    """上报test_result。"""
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
    """执行 interlock_check。"""
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
    """列出locked_workpieces。"""
    return workpiece_repo.list_locked()


def unlock_workpiece(workpiece, operator, reason, confirmed=False, target_step=None, note=None) -> dict:
    """解锁workpiece。"""
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
            wp_row=wp_row, operator=operator, reason=reason, confirmed=confirmed, now=now,
            target_step=target_step, note=note,
        )
    except InvariantViolation as exc:
        raise ValidationError(str(exc)) from exc


def list_unlock_logs(limit: int = 50) -> list[dict]:
    """列出unlock_logs。"""
    return log_repo.list_unlock_logs(limit=limit)


def list_upstream_rules() -> list[dict]:
    """列出upstream_rules。"""
    return upstream_repo.list_rules()


def replace_upstream_rules(rows: Iterable[dict]) -> int:
    """替换upstream_rules。"""
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
    """列出devices。"""
    return upstream_repo.list_devices()


def station_summary(device_id: str) -> dict | None:
    """按设备读取看板汇总；供 UI 通过 HTTP 获取。"""
    return station_repo.get_by_device(device_id)


def station_fail_details(device_id: str, limit: int = 50) -> list[dict]:
    """按设备读取失败项明细；供 UI 通过 HTTP 获取。"""
    return station_repo.list_fail_details(device_id, limit=limit)


# -----------------------------------------------------------------------------
# 看板统计
# -----------------------------------------------------------------------------
def dashboard_snapshot(device_filter: str | None = None) -> dict:
    """执行 dashboard_snapshot。"""
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
    """执行 coerce_variable_value。"""
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
    """执行 typed_variable_value。"""
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
    """执行 variable_public。"""
    return {
        "name": row["name"],
        "type": row["type"],
        "value": typed_variable_value(row["type"], row["value"]),
        "raw_value": row["value"],
        "last_device": row["last_device"],
        "updated_at": row["updated_at"],
    }


def list_variables(prefix: str = "") -> list[dict]:
    """列出variables。"""
    return [_variable_public(row) for row in variable_repo.list_variables(prefix=prefix)]


def get_variable(name: str, device_id: str | None = None) -> dict:
    """获取variable。"""
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
    """执行 add_variable。"""
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
    """设置variable。"""
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
    """执行 validate_variable_name。"""
    name = "" if name is None else str(name).strip()
    if not name:
        raise ValidationError("变量名不能为空")
    if not _VARIABLE_NAME_RE.match(name):
        raise ValidationError("变量名只能包含英文字母、数字、下划线、点和短横线，且以字母或下划线开头（长度 ≤ 64）")
    return name


def delete_variable(name: str) -> dict:
    """删除variable。"""
    name = _clean_text(name, "变量名", max_len=64)
    with _tx() as conn:
        if not variable_repo.exists(conn, name):
            raise NotFoundError(f"变量 {name} 不存在")
        variable_repo.delete_variable(conn, name)
    return {"name": name, "deleted": True}


def rename_variable(old_name: str, new_name: str) -> dict:
    """执行 rename_variable。"""
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
    """列出variable_logs。"""
    return variable_repo.list_logs(action=action, limit=limit)



# -----------------------------------------------------------------------------
# 产品查询/追溯（只读；解绑复用 unlock_workpiece）
# -----------------------------------------------------------------------------
def query_workpieces(**kwargs) -> list[dict]:
    """查询workpieces。"""
    return product_query_repo.list_workpieces(**kwargs)


def workpiece_detail(workpiece: str) -> dict | None:
    """执行 workpiece_detail。"""
    return product_query_repo.get_workpiece(workpiece)


def workpiece_test_history(workpiece: str) -> list[dict]:
    """测试履历：优先 V1.3 整单（主子表），无则回退旧 test_results 单条。"""
    reports = product_query_repo.test_reports_history(workpiece)
    if reports:
        return reports
    return product_query_repo.test_history(workpiece)


def workpiece_unlock_history(workpiece: str) -> list[dict]:
    """执行 workpiece_unlock_history。"""
    return product_query_repo.unlock_history(workpiece)


def product_route_detail(product_model: str) -> dict:
    """执行 product_route_detail。"""
    return {
        "info": product_query_repo.product_info(product_model),
        "route": product_query_repo.product_route(product_model),
    }


def distinct_products() -> list[str]:
    """执行 distinct_products。"""
    return product_query_repo.distinct_products()


# -----------------------------------------------------------------------------
# 工位操作台：产品 -> 工艺 -> 载具 -> 条码入站
# -----------------------------------------------------------------------------
def _split_csv(value: Any) -> list[str]:
    """执行 split_csv。"""
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _route_sort_key(route: dict) -> tuple[int, int | str]:
    """执行 route_sort_key。"""
    step_no = str(route.get("step_no") or "")
    return (0, int(step_no)) if step_no.isdigit() else (1, step_no)


def _workbench_recipe(conn: Conn, product_model: str) -> dict:
    """执行 workbench_recipe。"""
    product = next(
        (
            item
            for item in master_data_repo.list_products(conn)
            if str(item.get("product_model")) == product_model
        ),
        None,
    )
    if product is None:
        raise NotFoundError(f"产品型号 {product_model} 不存在")
    if not bool(product.get("enabled")):
        raise ValidationError(f"产品型号 {product_model} 已停用")

    processes = [
        item
        for item in master_data_repo.list_processes(conn)
        if str(item.get("component_no") or "") == product_model
        and bool(item.get("enabled"))
    ]
    if not processes:
        raise ValidationError(f"产品型号 {product_model} 未绑定启用工艺")
    if len(processes) > 1:
        codes = "、".join(str(item["process_code"]) for item in processes)
        raise ConflictError(f"产品型号 {product_model} 绑定了多个启用工艺：{codes}")

    process = processes[0]
    process_code = str(process["process_code"])
    routes = sorted(
        [
            row
            for row in master_data_repo.list_process_routes(conn)
            if str(row.get("process_code")) == process_code
        ],
        key=_route_sort_key,
    )
    if not routes:
        raise ValidationError(f"工艺 {process_code} 未配置工序路线")

    resources = [
        row
        for row in master_data_repo.list_process_step_resources(conn)
        if str(row.get("process_code")) == process_code
    ]
    tray_models_by_step: dict[str, list[str]] = {}
    for resource in resources:
        step_no = str(resource.get("step_no") or "")
        for model in _split_csv(resource.get("tray_models")):
            tray_models_by_step.setdefault(step_no, [])
            if model not in tray_models_by_step[step_no]:
                tray_models_by_step[step_no].append(model)
    tray_models: list[str] = []
    for resource in resources:
        for model in _split_csv(resource.get("tray_models")):
            if model not in tray_models:
                tray_models.append(model)
    if not tray_models:
        raise ValidationError(f"工艺 {process_code} 未配置转运载具型号")

    step_names = {
        str(step["step_no"]): str(step.get("step_name") or "")
        for step in master_data_repo.list_steps(conn)
    }
    route_details = [
        {
            **route,
            "step_name": step_names.get(str(route.get("step_no")), ""),
            "tray_models": tray_models_by_step.get(
                str(route.get("step_no")), []
            ),
        }
        for route in routes
    ]
    return {
        "product": product,
        "process": process,
        "routes": route_details,
        "steps": route_details,
        "tray_models": tray_models,
        "first_step": str(routes[0]["step_no"]),
        "first_success_next_step": str(routes[0]["success_next_step"]),
    }


def workbench_recipe(product_model: str) -> dict:
    """按产品型号倒查启用工艺、路线和允许的载具型号。"""
    product_model = _clean_text(product_model, "产品型号")
    with _read() as conn:
        return _workbench_recipe(conn, product_model)


def manual_inbound(
    *,
    product: str,
    step_no: str,
    traycode: str,
    barcodes: Iterable[str],
    operator: str,
) -> dict:
    """手动入站：产品、载具与载具载荷内的一批条码同时建档。"""
    product = _clean_text(product, "产品型号")
    step_no = _clean_text(step_no, "工序")
    traycode = _clean_text(traycode, "载具号")
    operator = _clean_text(operator, "操作员", max_len=64)
    cleaned_barcodes = [
        _clean_text(value, f"第 {index} 个条码")
        for index, value in enumerate(barcodes, start=1)
    ]
    if not cleaned_barcodes:
        raise ValidationError("入站条码不能为空")
    folded = [code.casefold() for code in cleaned_barcodes]
    if len(set(folded)) != len(folded):
        raise ValidationError("同一载具内的条码不能重复")

    with _read() as conn:
        recipe = _workbench_recipe(conn, product)
        route = next(
            (
                item
                for item in recipe["steps"]
                if str(item.get("step_no")) == step_no
            ),
            None,
        )
        if route is None:
            raise ValidationError(
                f"工序 {step_no} 不属于产品 {product} 的工艺 "
                f"{recipe['process']['process_code']}"
            )
        allowed_models = {
            model.casefold() for model in route["tray_models"]
        }
        if not allowed_models:
            raise ValidationError(
                f"产品 {product} 的工序 {step_no} 未配置允许的载具型号"
            )
        tray = next(
            (
                item
                for item in master_data_repo.list_trays(conn)
                if str(item.get("traycode")) == traycode
            ),
            None,
        )
        if tray is None:
            raise NotFoundError(f"载具 {traycode} 不存在")
        if not bool(tray.get("enabled")):
            raise ValidationError(f"载具 {traycode} 已停用")
        if str(tray.get("tray_model") or "").casefold() not in allowed_models:
            raise ValidationError(
                f"载具 {traycode} 的型号 {tray.get('tray_model')} 不符合"
                f"产品 {product}、工序 {step_no} 的允许范围"
            )
        capacity = int(tray.get("capacity") or 0)
        if capacity <= 0:
            raise ValidationError(f"载具 {traycode} 未配置有效载荷数量")
        if product_flow_store.list_overview(traycode=traycode):
            raise ConflictError(
                f"载具 {traycode} 当前已绑定产品，请先解除托盘绑定"
            )
        if len(cleaned_barcodes) > capacity:
            raise ValidationError(
                f"载具 {traycode} 最多可填写 {capacity} 个条码"
            )
        # 工件主表可能由测试上报产生，不能作为“当前入站占用”的判定依据；
        # 入站占用只看 ProductFlow 当前总览。

    for barcode in cleaned_barcodes:
        if product_flow_store.get_overview_by_barcode(barcode) is not None:
            raise ConflictError(f"条码 {barcode} 已存在，不能重复入站")

    now = db.utc_now_iso()
    rows = [
        {
            "barcode": barcode,
            "componentcode": product,
            "traycode": traycode,
            "board_status": "normal",
            "step_no": step_no,
            "next_step": str(route["success_next_step"]),
            "device": "手动入站",
            "note": f"手动入站（操作员：{operator}）",
        }
        for barcode in cleaned_barcodes
    ]
    _station_workbench_uc.manual_inbound(rows=rows, now=now)
    return {
        "product": product,
        "traycode": traycode,
        "process_code": str(recipe["process"]["process_code"]),
        "current_step": step_no,
        "next_step": str(route["success_next_step"]),
        "count": len(cleaned_barcodes),
        "barcodes": cleaned_barcodes,
    }


def unbind_tray(*, traycode: str, operator: str, confirmed: bool) -> dict:
    """解除托盘与产品的当前绑定，并为每个产品写明操作留痕。"""
    traycode = _clean_text(traycode, "载具号")
    operator = _clean_text(operator, "操作员", max_len=64)
    if not confirmed:
        raise ValidationError("必须勾选确认后才能解绑托盘")
    if not product_flow_store.list_overview(traycode=traycode):
        raise NotFoundError(f"载具 {traycode} 当前未绑定产品")
    affected = _station_workbench_uc.unbind_tray(
        traycode=traycode,
        operator=operator,
        now=db.utc_now_iso(),
    )
    if not affected:
        raise NotFoundError(f"载具 {traycode} 当前未绑定产品")
    return {
        "traycode": traycode,
        "count": len(affected),
        "barcodes": [str(item["barcode"]) for item in affected],
    }


def delete_product_flow(*, barcode: str) -> dict:
    """删除指定产品的入线状态及 ProductFlow 历史。"""
    barcode = _clean_text(barcode, "产品条码")
    deleted = _station_workbench_uc.delete_product_flow(barcode=barcode)
    if deleted is None:
        raise NotFoundError(f"产品 {barcode} 当前没有入线状态")
    return {"barcode": barcode}


def delete_tray_flow(*, traycode: str) -> dict:
    """删除指定托盘当前全部在制产品状态。"""
    traycode = _clean_text(traycode, "载具号")
    deleted = _station_workbench_uc.delete_tray_flow(traycode=traycode)
    if not deleted:
        raise NotFoundError(f"载具 {traycode} 当前没有在制产品")
    return {
        "traycode": traycode,
        "count": len(deleted),
        "barcodes": [str(item["barcode"]) for item in deleted],
    }


def repair_tray_operation_report_fields() -> dict:
    """修复历史托盘操作覆盖的最近设备/说明；产品解锁记录保留。"""
    from .repositories import product_flow_store

    purged = product_flow_store.purge_tray_events_from_flow_details()
    rows = product_flow_store.list_overview()
    repaired = 0
    for row in rows:
        device = str(row.get("last_report_device") or "")
        if device not in {"托盘解绑", "托盘自动解绑"}:
            continue
        if product_flow_store.restore_last_report_from_flow(
            barcode=str(row["barcode"]),
            changed_at=str(row.get("updated_at") or ""),
        ):
            repaired += 1
    return {"repaired": repaired, "purged_flow_events": purged}
