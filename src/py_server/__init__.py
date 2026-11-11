"""旁路式小型 MES（设备乙方内部使用）。

启动方式见 README.md；安装后也可以直接运行 ``py-server`` 查看命令提示。
"""

from __future__ import annotations

__version__ = "0.1.0"


def main() -> None:
    print(
        "旁路式小型 MES\n"
        "  初始化演示数据： python -m py_server.seed --reset --demo\n"
        "  启动设备接口：   .\\scripts\\run_api.ps1\n"
        "  启动页面：       .\\scripts\\run_ui.ps1\n"
        "  运行测试：       uv run pytest"
    )


if __name__ == "__main__":
    main()
