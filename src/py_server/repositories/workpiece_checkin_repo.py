"""产品进站校验的只读查询。SQL 只出现在本模块。"""

from __future__ import annotations

from sqlalchemy import select

from .. import engine as eg
from .base import Conn


def _split_models(value: object) -> tuple[str, ...]:
    """把逗号分隔的型号配置拆成集合。"""
    return tuple({item.strip() for item in str(value or "").split(",") if item.strip()})


def find_active_product(conn: Conn, barcode: str) -> dict | None:
    """按条码查询当前在制产品。"""
    row = conn.execute(
        select(eg.active_products).where(eg.active_products.c.barcode == barcode)
    ).fetchone()
    return dict(row) if row is not None else None


def find_product_model(conn: Conn, barcode: str) -> str:
    """查询工件主数据中的产品型号。"""
    row = conn.execute(
        select(eg.workpieces.c.product).where(eg.workpieces.c.workpiece == barcode)
    ).fetchone()
    return str(row[0] or "") if row is not None else ""


def find_process_for_product(conn: Conn, componentcode: str) -> dict | None:
    """按产品型号查询启用的工艺。"""
    row = conn.execute(
        select(eg.processes)
        .where(eg.processes.c.component_no == componentcode, eg.processes.c.enabled == 1)
        .order_by(eg.processes.c.process_code)
        .limit(1)
    ).fetchone()
    return dict(row) if row is not None else None


def find_process_route(conn: Conn, process_code: str, step_no: str) -> dict | None:
    """查询工艺路线中的指定工序。"""
    row = conn.execute(
        select(eg.process_routes).where(
            eg.process_routes.c.process_code == process_code,
            eg.process_routes.c.step_no == step_no,
        )
    ).fetchone()
    return dict(row) if row is not None else None


def find_step_resource(conn: Conn, process_code: str, step_no: str) -> dict | None:
    """查询工序资源配置并把型号字段规范化为集合。"""
    row = conn.execute(
        select(eg.process_step_resources).where(
            eg.process_step_resources.c.process_code == process_code,
            eg.process_step_resources.c.step_no == step_no,
        )
    ).fetchone()
    if row is None:
        return None
    data = dict(row)
    data["device_model_set"] = _split_models(data.get("device_models"))
    data["tray_model_set"] = _split_models(data.get("tray_models"))
    data["needle_bed_model_set"] = _split_models(data.get("needle_bed_models"))
    return data


def find_device(conn: Conn, station: str) -> dict | None:
    """按工位编号查询设备主数据。"""
    row = conn.execute(
        select(eg.devices).where(eg.devices.c.device_id == station)
    ).fetchone()
    return dict(row) if row is not None else None


def find_needle_bed(conn: Conn, fixturecode: str) -> dict | None:
    """按治具编号查询针床主数据。"""
    row = conn.execute(
        select(eg.needle_beds).where(eg.needle_beds.c.needle_bed_code == fixturecode)
    ).fetchone()
    return dict(row) if row is not None else None


def find_tray(conn: Conn, traycode: str) -> dict | None:
    """按载具号查询载具主数据。"""
    row = conn.execute(
        select(eg.trays).where(eg.trays.c.traycode == traycode)
    ).fetchone()
    return dict(row) if row is not None else None


def find_binding(conn: Conn, station: str, componentcode: str):
    """查询设备与产品的程序绑定，供既有可信性规则复用。"""
    from . import binding_repo

    return binding_repo.try_binding(conn, station, componentcode)


def upstream_devices(conn: Conn, componentcode: str, station: str) -> list[str]:
    """查询前道关键设备。"""
    from . import upstream_repo

    return upstream_repo.upstream_devices(conn, componentcode, station)


def has_trusted_pass(conn: Conn, *, barcode: str, device_id: str, componentcode: str) -> bool:
    """沿用既有前道可信 PASS 判定。"""
    from . import upstream_repo

    return upstream_repo.has_trusted_pass(
        conn, workpiece=barcode, device_id=device_id, product=componentcode
    )
