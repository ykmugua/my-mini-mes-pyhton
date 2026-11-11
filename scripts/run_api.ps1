# 启动设备侧接口服务（FastAPI）
param(
    [string]$BindAddress = "0.0.0.0",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "未找到虚拟环境：$python，请先在 py-server 目录执行 uv sync"
}

Set-Location $root
$env:MES_API_PORT = "$Port"
Write-Host "接口服务启动：http://${BindAddress}:$Port"
Write-Host "设备请使用 http://<本机内网IP>:$Port 访问（程序下载地址同源）"
& $python -m uvicorn py_server.api:app --host $BindAddress --port $Port
