# 一键启动本地接口服务与页面服务。
param(
    [string]$BindAddress = "0.0.0.0",
    [int]$ApiPort = 8000,
    [int]$UIPort = 8501,
    [string]$ApiBase = ""
)

$ErrorActionPreference = "Stop"

$root = Split-Path $PSScriptRoot -Parent
$python = Join-Path $root ".venv\Scripts\python.exe"
$apiScript = Join-Path $PSScriptRoot "run_api.ps1"
$uiScript = Join-Path $PSScriptRoot "run_ui.ps1"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Virtual environment not found: $python. Run 'uv sync' first."
}
if (-not (Test-Path -LiteralPath $apiScript)) {
    throw "API start script not found: $apiScript"
}
if (-not (Test-Path -LiteralPath $uiScript)) {
    throw "UI start script not found: $uiScript"
}

if ([string]::IsNullOrWhiteSpace($ApiBase)) {
    $ApiBase = "http://127.0.0.1:$ApiPort"
}

$logDir = Join-Path $env:TEMP "mini-mes-service-logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null

function Test-PortListening {
    param([int]$Port)
    $conn = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -eq $Port }
    return [bool]$conn
}

function Start-ServiceProcess {
    param(
        [string]$Label,
        [string]$ScriptPath,
        [string[]]$Arguments,
        [string]$OutLog,
        [string]$ErrLog
    )

    $powershellExe = "pwsh"
    $command = Get-Command $powershellExe -ErrorAction SilentlyContinue
    if (-not $command) {
        $powershellExe = "powershell"
    }

    Write-Host "Starting ${Label}..."
    Start-Process `
        -FilePath $powershellExe `
        -ArgumentList (@(
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", $ScriptPath
        ) + $Arguments) `
        -WorkingDirectory $root `
        -WindowStyle Hidden `
        -RedirectStandardOutput $OutLog `
        -RedirectStandardError $ErrLog
}

if (Test-PortListening -Port $ApiPort) {
    Write-Warning "Port $ApiPort is already listening; skip API service."
} else {
    Start-ServiceProcess `
        -Label "API" `
        -ScriptPath $apiScript `
        -Arguments @("-BindAddress", $BindAddress, "-Port", "$ApiPort") `
        -OutLog (Join-Path $logDir "api.log") `
        -ErrLog (Join-Path $logDir "api.err.log")
}

if (Test-PortListening -Port $UIPort) {
    Write-Warning "Port $UIPort is already listening; skip UI service."
} else {
    Start-ServiceProcess `
        -Label "UI" `
        -ScriptPath $uiScript `
        -Arguments @("-BindAddress", $BindAddress, "-Port", "$UIPort", "-ApiBase", $ApiBase) `
        -OutLog (Join-Path $logDir "ui.log") `
        -ErrLog (Join-Path $logDir "ui.err.log")
}

function Wait-ForHttpOk {
    param(
        [string]$Label,
        [string]$Url,
        [int]$TimeoutSeconds = 20
    )

    for ($i = 0; $i -lt $TimeoutSeconds; $i++) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
            if ($response.StatusCode -eq 200) {
                Write-Host "$Label ready: $Url"
                return
            }
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    Write-Warning "$Label did not become ready within $TimeoutSeconds seconds: $Url"
}

Wait-ForHttpOk -Label "API" -Url "http://127.0.0.1:$ApiPort/health"
Wait-ForHttpOk -Label "UI" -Url "http://127.0.0.1:$UIPort/_stcore/health"

Write-Host "Logs: $logDir"
