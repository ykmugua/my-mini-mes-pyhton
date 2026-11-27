"""产品进站校验用例：只读判定，不产生任何状态变更。"""

from __future__ import annotations

from dataclasses import dataclass

from ..constants import is_missing_traycode
from ..domain.interlock.policy import InterlockPolicy, InterlockReason
from ..domain.trust.verdict import TrustVerdict
from ..domain.workpiece.model import Workpiece
from ..repositories import workpiece_checkin_repo
from ..repositories.base import Conn, with_read_conn


@dataclass(frozen=True)
class CheckInRequest:
    """application 层输入，不依赖 FastAPI。"""

    barcode: str
    station: str
    fixturecode: str
    traycode: str


@dataclass(frozen=True)
class CheckInResult:
    """application 层输出，不依赖 FastAPI。"""

    success: bool
    code: str
    message: str
    processcode: str = ""
    stepon: str = ""

    def envelope(self) -> dict:
        """转换成接口业务信封。"""
        return {
            "success": self.success,
            "code": self.code,
            "message": self.message,
            "data": (
                {"processcode": self.processcode, "stepon": self.stepon}
                if self.success
                else None
            ),
        }


def _reject(message: str) -> CheckInResult:
    """构造统一失败结果。"""
    return CheckInResult(False, "400", f"产品进站失败：{message}")


def _check_interlock(conn: Conn, request: CheckInRequest, componentcode: str, stepon: str) -> str:
    """复用现有锁定、FAIL 和前道放行规则；不检查当前设备程序。"""
    from ..repositories import workpiece_repo

    wp_row = workpiece_repo.get_workpiece(conn, request.barcode)
    workpiece = Workpiece.from_row(wp_row) if wp_row else None
    upstreams = tuple(workpiece_checkin_repo.upstream_devices(conn, componentcode, request.station))
    trusted_pass = tuple(
        upstream
        for upstream in upstreams
        if workpiece_checkin_repo.has_trusted_pass(
            conn,
            barcode=request.barcode,
            device_id=upstream,
            componentcode=componentcode,
        )
    )
    decision = InterlockPolicy.evaluate(
        workpiece=workpiece,
        device_id=request.station,
        product=componentcode,
        trust=TrustVerdict.ok(),
        upstreams=upstreams,
        trusted_pass_upstreams=trusted_pass,
        trust_detail="",
    )
    if decision.allowed:
        return ""
    if decision.reason is InterlockReason.WORKPIECE_LOCKED:
        return "该产品当前处于锁定状态，测试结果为FAIL"
    if decision.reason is InterlockReason.WORKPIECE_FAILED:
        return "该产品测试结果为FAIL"
    if decision.reason is InterlockReason.UPSTREAM_MISSING:
        return "前道工序未完成：" + "、".join(decision.upstream_missing)
    return decision.detail or "产品状态不允许进站"


def execute(request: CheckInRequest, *, conn: Conn | None = None) -> CheckInResult:
    """执行只读进站资格校验。"""
    if conn is not None:
        return _execute(conn, request)
    with with_read_conn() as own_conn:
        return _execute(own_conn, request)


def _execute(conn: Conn, request: CheckInRequest) -> CheckInResult:
    """在只读连接中执行全部查询。"""
    active = workpiece_checkin_repo.find_active_product(conn, request.barcode)
    componentcode = str((active or {}).get("componentcode") or "")
    if not componentcode:
        componentcode = workpiece_checkin_repo.find_product_model(conn, request.barcode)
    if not active and not componentcode:
        return _reject("产品不存在")
    if active and not is_missing_traycode(request.traycode):
        bound_traycode = str(active.get("traycode") or "")
        if bound_traycode != request.traycode:
            return _reject(
                f"产品 {request.barcode} 当前绑定载具为 {bound_traycode or '/'}，"
                f"与请求载具 {request.traycode} 不匹配"
            )

    process = workpiece_checkin_repo.find_process_for_product(conn, componentcode)
    if process is None:
        return _reject("未找到产品对应的工艺配置")
    processcode = str(process["process_code"])

    stepon = str((active or {}).get("current_step") or "")
    if not stepon:
        return _reject("缺少产品当前应执行工序")
    if workpiece_checkin_repo.find_process_route(conn, processcode, stepon) is None:
        return _reject(f"工艺 {processcode} 未配置工序 {stepon}")

    resource = workpiece_checkin_repo.find_step_resource(conn, processcode, stepon)
    if resource is None:
        return _reject(f"工艺 {processcode} 工序 {stepon} 的工序资源配置不存在")

    device = workpiece_checkin_repo.find_device(conn, request.station)
    if device is None:
        return _reject(f"当前工位 {request.station} 未注册")
    device_model = str(device.get("device_model") or "")
    if not device_model:
        return _reject(f"当前工位 {request.station} 缺少设备型号配置")
    if device_model not in resource["device_model_set"]:
        return _reject(
            f"当前工位 {request.station} 的设备型号 {device_model} "
            f"与工序要求型号 {'/'.join(resource['device_model_set'])} 不匹配"
        )
    if resource["needle_bed_model_set"]:
        needle_bed = workpiece_checkin_repo.find_needle_bed(conn, request.fixturecode)
        if needle_bed is None:
            return _reject(f"当前治具 {request.fixturecode} 未注册")
        needle_bed_model = str(needle_bed.get("needle_bed_model") or "")
        if not needle_bed_model:
            return _reject(f"当前治具 {request.fixturecode} 缺少治具型号配置")
        if needle_bed_model not in resource["needle_bed_model_set"]:
            return _reject(
                f"当前治具 {request.fixturecode} 的型号为 {needle_bed_model}，"
                f"与工序要求的型号 {'/'.join(resource['needle_bed_model_set'])} 不匹配"
            )

    if resource["tray_model_set"]:
        tray = workpiece_checkin_repo.find_tray(conn, request.traycode)
        if tray is None:
            return _reject(f"当前托盘 {request.traycode} 未注册")
        tray_model = str(tray.get("tray_model") or "")
        if not tray_model:
            return _reject(f"当前托盘 {request.traycode} 缺少托盘型号配置")
        if tray_model not in resource["tray_model_set"]:
            return _reject(
                f"当前托盘 {request.traycode} 的型号为 {tray_model}，"
                f"与工序要求的型号 {'/'.join(resource['tray_model_set'])} 不匹配"
            )

    interlock_error = _check_interlock(conn, request, componentcode, stepon)
    if interlock_error:
        return _reject(interlock_error)
    return CheckInResult(True, "200", "产品允许进站", processcode=processcode, stepon=stepon)
