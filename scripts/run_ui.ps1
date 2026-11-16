# Start Streamlit UI (HTTP-only; FastAPI must be running)
param(
    [string]$BindAddress = "0.0.0.0",
    [int]$Port = 8501,
    [string]$ApiBase = "http://127.0.0.1:8000"
)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "Virtual environment not found: $python. Run 'uv sync' first."
}

Set-Location $root
# Streamlit talks to FastAPI over HTTP only. Set explicit base URL to avoid
# probing the wrong LAN IP (which caused WinError 10061).
$env:MES_UI_API_BASE = $ApiBase
Write-Host "UI:      http://${BindAddress}:$Port"
Write-Host "API base: $env:MES_UI_API_BASE"
& $python -m streamlit run src\py_server\streamlit_app.py --server.address $BindAddress --server.port $Port