# 一键停止本地接口服务与页面服务。
param(
    [int]$ApiPort = 8000,
    [int]$UIPort = 8501
)

$ErrorActionPreference = "Stop"

$ports = @($ApiPort, $UIPort)
$processes = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $ports -contains $_.LocalPort } |
    Select-Object -ExpandProperty OwningProcess -Unique

if (-not $processes) {
    Write-Host "No service listening on ports $($ports -join ', ')."
    exit 0
}

foreach ($procId in $processes) {
    $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($proc) {
        Write-Host "Stopping PID $procId ($($proc.ProcessName))..."
    } else {
        Write-Host "Stopping PID $procId..."
    }
    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
}

Start-Sleep -Seconds 1
$remaining = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $ports -contains $_.LocalPort }

if ($remaining) {
    Write-Warning "Some ports are still listening:"
    $remaining | Select-Object LocalPort, OwningProcess | Format-Table -AutoSize
    exit 1
}

Write-Host "Services stopped."
