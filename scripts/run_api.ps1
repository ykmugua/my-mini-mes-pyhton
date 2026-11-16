# Start FastAPI server (owns the database; Streamlit talks to it over HTTP)
param(
    [string]$BindAddress = "0.0.0.0",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "Virtual environment not found: $python. Run 'uv sync' first."
}

Set-Location $root
$env:MES_API_PORT = "$Port"
Write-Host "API:     http://${BindAddress}:$Port"
Write-Host "Devices should use http://<LAN-IP>:$Port (program downloads use the same origin)"
& $python -m uvicorn py_server.api:app --host $BindAddress --port $Port