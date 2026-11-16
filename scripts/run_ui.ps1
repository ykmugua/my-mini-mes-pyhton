# 启动 Streamlit 页面
param(
    [string]$BindAddress = "0.0.0.0",
    [int]$Port = 8501,
    [string]$ApiBase = "http://127.0.0.1:8000"
)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "未找到虚拟环境：$python，请先在 py-server 目录执行 uv sync"
}

Set-Location $root
# Streamlit 只通过 HTTP 访问 FastAPI；显式设置避免自动探测内网 IP 出错。
$env:MES_UI_API_BASE = $ApiBase
Write-Host "页面服务启动：http://${BindAddress}:$Port"
Write-Host "接口服务地址：$env:MES_UI_API_BASE"
& $python -m streamlit run src\py_server\streamlit_app.py --server.address $BindAddress --server.port $Port