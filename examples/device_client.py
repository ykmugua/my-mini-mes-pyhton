#!/usr/bin/env python
"""设备侧参考客户端（示例代码）。

演示设备端需要具备的几项能力：

* 幂等上报：服务端按 (工件码, 设备, 测试项) 去重，重复上报不会重复计；
* 上传失败本地缓存补传：上报失败先写入本地队列，`flush` 时重试；
* 程序下载中断续传：使用 HTTP Range 续传，完成后校验 SHA256，不匹配则重下。
* 设备开启状态：通过 `GET /api/device/enable` 查询，设备端不直接读取配置文件。
* 设备在线与测试开始：通过 `POST /api/device/heartbeat` 与 `POST /api/device/test-start` 上报。

用法示例::

    python examples/device_client.py --device TEST-01 --product P-1001 demo

    python examples/device_client.py --device TEST-01 --product P-1001 pull
    python examples/device_client.py --device TEST-01 --product P-1001 status
    python examples/device_client.py --device TEST-01 report \\
        --workpiece WP-0001 --item 上电电流 --result PASS
    python examples/device_client.py --device TEST-01 interlock --workpiece WP-0001
    python examples/device_client.py --device TEST-01 var-get --name line_mode
    python examples/device_client.py --device TEST-01 var-set --name line_mode --value MANUAL
    python examples/device_client.py --device TEST-01 enabled
    python examples/device_client.py --device TEST-01 heartbeat
    python examples/device_client.py --device TEST-01 test-start --workpiece WP-0001
    python examples/device_client.py --device TEST-01 flush
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


class DeviceClient:
    """一个测试设备的 HTTP 客户端。"""

    def __init__(
        self,
        base_url: str,
        device_id: str,
        product: str | None = None,
        cache_dir: str | Path = ".device-cache",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.device_id = device_id
        self.product = product
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.outbox = self.cache_dir / f"outbox-{device_id}.jsonl"
        self.http = httpx.Client(base_url=self.base_url, timeout=30)

    # -- 基础请求 ---------------------------------------------------------
    def close(self) -> None:
        self.http.close()

    def _program_params(self) -> dict[str, str]:
        params = {"device_id": self.device_id}
        if self.product:
            params["product"] = self.product
        return params

    def get_program(self) -> dict[str, Any]:
        response = self.http.get("/api/program", params=self._program_params())
        response.raise_for_status()
        return response.json()

    def report_status(
        self, program_version: str, sha256: str, sha256_ok: bool = True
    ) -> dict[str, Any]:
        payload = {
            "device_id": self.device_id,
            "program_version": program_version,
            "sha256": sha256,
            "sha256_ok": sha256_ok,
        }
        if self.product:
            payload["product"] = self.product
        response = self.http.post("/api/program/status", json=payload)
        response.raise_for_status()
        return response.json()

    def check_interlock(self, workpiece: str) -> dict[str, Any]:
        params = {"workpiece": workpiece, "device_id": self.device_id}
        if self.product:
            params["product"] = self.product
        response = self.http.get("/api/interlock", params=params)
        response.raise_for_status()
        return response.json()

    # -- 测试结果上报（V1.3 整单 + 失败入队补传） ------------------------------
    def report_result(
        self,
        workpiece: str,
        test_item: str,
        result: str,
        measured_value: Any = None,
        program_version: str | None = None,
        program_sha256: str | None = None,
    ) -> dict[str, Any]:
        """上报一条 V1.3 整单测试结果；失败时写入本地 outbox。"""
        detail_result = "true" if result == "PASS" else "false"
        payload = {
            "station": self.device_id,
            "componentcode": self.product or "",
            "traycode": "",
            "barcode": workpiece,
            "programname": "DEVICE-CLIENT",
            "programversion": program_version or "v1",
            "testexecutetime": "2026/11/24 10:00:00.000",
            "testlongtime": "00:00:01.000",
            "result": result,
            "isfinalreport": "false",
            "details": [
                {
                    "TestItem": test_item,
                    "TestStep": test_item,
                    "StandardValue": "1.00",
                    "UpperValue": "2.00",
                    "LowerValue": "0.00",
                    "MeasureValue": str(measured_value or ""),
                    "TestResult": detail_result,
                    "TestBeginTime": "10:00:00.000",
                    "TestEndTime": "10:00:01.000",
                }
            ],
        }
        try:
            return self._post_result(payload)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code < 500:
                raise
            self._enqueue(payload)
            return {"queued": True, "reason": f"HTTP {exc.response.status_code}"}
        except httpx.HTTPError as exc:
            self._enqueue(payload)
            return {"queued": True, "reason": str(exc)}

    def _post_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        """向 V1.3 整单接口提交 payload，并返回业务 result。"""
        request_id = f"client-{payload['barcode']}-{int(time.time() * 1000)}"[:32]
        response = self.http.post(
            "/api/v1/test-results",
            json=payload,
            headers={
                "x-device-sn": payload["station"],
                "x-timestamp": str(int(time.time() * 1000)),
                "x-request-id": request_id,
            },
        )
        response.raise_for_status()
        envelope = response.json()
        if envelope.get("code") != 0:
            raise httpx.HTTPStatusError(
                envelope.get("message", "upload failed"),
                request=response.request,
                response=response,
            )
        return envelope["result"]

    def _enqueue(self, payload: dict[str, Any]) -> None:
        """同一工件+设备+测试项只保留一条待补传记录。"""
        key = (payload["barcode"], payload["station"], payload["details"][0]["TestStep"])
        records: dict[tuple[str, str, str], dict[str, Any]] = {}
        if self.outbox.exists():
            for line in self.outbox.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                item = json.loads(line)
                records[(item["barcode"], item["station"], item["details"][0]["TestStep"])] = item
        records[key] = payload
        with self.outbox.open("w", encoding="utf-8") as handle:
            for item in records.values():
                handle.write(json.dumps(item, ensure_ascii=False) + "\n")

    def flush_outbox(self) -> dict[str, int]:
        """重试本地缓存的待补传数据，返回成功/剩余数量。"""
        if not self.outbox.exists():
            return {"sent": 0, "remaining": 0}
        records = [
            json.loads(line)
            for line in self.outbox.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        remaining: list[dict[str, Any]] = []
        sent = 0
        for payload in records:
            try:
                self._post_result(payload)
                sent += 1
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code >= 500:
                    remaining.append(payload)
                # 4xx 说明数据本身有问题，丢弃并计数为失败
            except httpx.HTTPError:
                remaining.append(payload)
        if remaining:
            with self.outbox.open("w", encoding="utf-8") as handle:
                for payload in remaining:
                    handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        else:
            self.outbox.unlink(missing_ok=True)
        return {"sent": sent, "remaining": len(remaining)}

    # -- 程序下载（断点续传 + 校验和） ------------------------------------
    def download_program(self, target: str | Path | None = None) -> Path:
        metadata = self.get_program()
        expected = metadata["sha256"].lower()
        url = metadata["download_url"]
        if target is None:
            name = Path(url.split("?")[0]).name or "program.bin"
            target = self.cache_dir / name
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists() and sha256_file(target) == expected:
            return target

        part = target.with_name(target.name + ".part")
        for attempt in range(2):
            self._download_once(url, part)
            if part.exists() and sha256_file(part) == expected:
                part.replace(target)
                return target
            part.unlink(missing_ok=True)
            if attempt == 0:
                print("SHA256 校验失败，删除临时文件后重试完整下载…", file=sys.stderr)
        raise RuntimeError("程序下载失败：SHA256 校验不通过")

    def _download_once(self, url: str, part: Path) -> None:
        headers: dict[str, str] = {}
        mode = "wb"
        if part.exists() and part.stat().st_size > 0:
            headers["Range"] = f"bytes={part.stat().st_size}-"
            mode = "ab"
        with self.http.stream("GET", url, headers=headers) as response:
            if response.status_code == 416:  # 续传位置恰好等于文件长度
                return
            if response.status_code == 206:
                mode = "ab"
            elif response.status_code == 200:
                mode = "wb"  # 服务端不支持 Range，重新完整下载
            else:
                response.raise_for_status()
            with part.open(mode) as handle:
                for chunk in response.iter_bytes(65536):
                    handle.write(chunk)

    # -- 开放变量 ---------------------------------------------------------
    def read_variable(self, name: str) -> dict[str, Any]:
        response = self.http.get(f"/api/variable/{name}")
        response.raise_for_status()
        return response.json()

    def write_variable(self, name: str, value: Any) -> dict[str, Any]:
        response = self.http.post(
            f"/api/variable/{name}",
            json={"value": value, "device_id": self.device_id},
        )
        response.raise_for_status()
        return response.json()

    def device_enabled(self) -> dict[str, Any]:
        response = self.http.get(
            "/api/device/enable", params={"device_id": self.device_id}
        )
        response.raise_for_status()
        return response.json()

    def heartbeat(self) -> dict[str, Any]:
        response = self.http.post(
            "/api/device/heartbeat", json={"device_id": self.device_id}
        )
        response.raise_for_status()
        return response.json()

    def test_start(self, workpiece: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"device_id": self.device_id}
        if workpiece:
            payload["workpiece"] = workpiece
        response = self.http.post("/api/device/test-start", json=payload)
        response.raise_for_status()
        return response.json()


def demo(client: DeviceClient, workpiece: str) -> None:
    """一次完整的设备交互：拉程序 -> 上报状态 -> 下载校验 -> 查锁 -> 报结果 -> 读变量。"""
    metadata = client.get_program()
    print("1. 拉取程序：", json.dumps(metadata, ensure_ascii=False, indent=2))
    status = client.report_status(
        metadata["program_version"], metadata["sha256"], sha256_ok=True
    )
    print("2. 上报程序状态：", json.dumps(status, ensure_ascii=False, indent=2))
    path = client.download_program()
    print(f"3. 程序下载并校验完成：{path}")

    interlock = client.check_interlock(workpiece)
    print("4. 放行查询：", json.dumps(interlock, ensure_ascii=False, indent=2))
    if not interlock["allowed"]:
        print("   设备拒绝启动测试，原因：", interlock["reason"])
        return
    result = client.report_result(
        workpiece,
        "上电电流",
        "PASS",
        measured_value="1.02A",
        program_version=metadata["program_version"],
        program_sha256=metadata["sha256"],
    )
    print("5. 上报测试结果：", json.dumps(result, ensure_ascii=False, indent=2))
    try:
        variable = client.read_variable("line_mode")
        print("6. 读取变量：", json.dumps(variable, ensure_ascii=False, indent=2))
    except httpx.HTTPStatusError as exc:
        print("6. 读取变量失败（演示库可能没有该变量）：", exc.response.status_code)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="旁路 MES 设备侧参考客户端")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="接口服务地址（默认 http://127.0.0.1:8000）",
    )
    parser.add_argument("--device", required=True, help="设备标识")
    parser.add_argument("--product", default=None, help="产品型号（设备只绑定一个产品时可省略）")
    parser.add_argument("--cache-dir", default=".device-cache", help="本地缓存目录")
    parser.add_argument("--workpiece", default="DEMO-WP-001", help="演示/查询用工件码")

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="跑一遍完整设备交互流程")
    sub.add_parser("pull", help="拉取程序元数据")
    sub.add_parser("status", help="用绑定版本上报程序状态")
    download = sub.add_parser("download", help="下载程序并校验 SHA256")
    download.add_argument("--target", default=None, help="保存路径")
    interlock = sub.add_parser("interlock", help="查询工件放行状态")

    report = sub.add_parser("report", help="上报一条测试结果")
    report.add_argument("--workpiece", required=True)
    report.add_argument("--item", required=True)
    report.add_argument("--result", default="PASS", choices=["PASS", "FAIL"])
    report.add_argument("--value", default=None)

    var_get = sub.add_parser("var-get", help="读取开放变量")
    var_get.add_argument("--name", required=True)
    var_set = sub.add_parser("var-set", help="写入开放变量")
    var_set.add_argument("--name", required=True)
    var_set.add_argument("--value", required=True)

    sub.add_parser("flush", help="补传本地缓存的测试结果")
    sub.add_parser("enabled", help="查询设备开启状态")
    sub.add_parser("heartbeat", help="上报设备心跳")
    test_start = sub.add_parser("test-start", help="上报测试开始")
    test_start.add_argument("--workpiece", default=None, help="测试中的工件条码")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    client = DeviceClient(args.base_url, args.device, args.product, args.cache_dir)
    try:
        if args.command == "demo":
            demo(client, args.workpiece)
        elif args.command == "pull":
            print(json.dumps(client.get_program(), ensure_ascii=False, indent=2))
        elif args.command == "status":
            metadata = client.get_program()
            print(
                json.dumps(
                    client.report_status(
                        metadata["program_version"], metadata["sha256"], True
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        elif args.command == "download":
            print(client.download_program(args.target))
        elif args.command == "interlock":
            print(
                json.dumps(
                    client.check_interlock(args.workpiece),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        elif args.command == "report":
            print(
                json.dumps(
                    client.report_result(
                        args.workpiece, args.item, args.result, args.value
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        elif args.command == "var-get":
            print(json.dumps(client.read_variable(args.name), ensure_ascii=False, indent=2))
        elif args.command == "var-set":
            print(
                json.dumps(
                    client.write_variable(args.name, args.value),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        elif args.command == "flush":
            print(json.dumps(client.flush_outbox(), ensure_ascii=False, indent=2))
        elif args.command == "enabled":
            print(json.dumps(client.device_enabled(), ensure_ascii=False, indent=2))
        elif args.command == "heartbeat":
            print(json.dumps(client.heartbeat(), ensure_ascii=False, indent=2))
        elif args.command == "test-start":
            print(json.dumps(client.test_start(args.workpiece), ensure_ascii=False, indent=2))
    finally:
        client.close()


if __name__ == "__main__":
    main()
