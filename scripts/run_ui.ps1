# 启动 Streamlit 页面
param(
    [string]$BindAddress = "0.0.0.0",
    [int]$Port = 8501
)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "未找到虚拟环境：$python，请先在 py-server 目录执行 uv sync"
}

Set-Location $root
Write-Host "页面服务启动：http://${BindAddress}:$Port"
& $python -m streamlit run src\py_server\streamlit_app.py --server.address $BindAddress --server.port $Port
