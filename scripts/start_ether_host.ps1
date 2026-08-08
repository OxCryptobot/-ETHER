# ETHER host launcher - always restarts unless clean Ctrl+C (code 0)
#
#   powershell -ExecutionPolicy Bypass -File .\scripts\start_ether_host.ps1

$ErrorActionPreference = "Continue"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not (Test-Path (Join-Path $Root "core"))) {
    $Root = (Get-Location).Path
}
Set-Location $Root

$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Write-Error "Missing $Py"
    exit 1
}

Write-Host "ETHER HOST | always-restart | http://127.0.0.1:8787/agent" -ForegroundColor Green
Write-Host "Ctrl+C to stop permanently" -ForegroundColor DarkGray
Write-Host ""

$failCount = 0

while ($true) {
    Write-Host "Sync origin/main..." -ForegroundColor Cyan
    git fetch origin 2>$null | Out-Null
    git reset --hard origin/main 2>&1 | Out-Host

    Write-Host "Starting ether_host..." -ForegroundColor Cyan
    & $Py "scripts\ether_host.py"
    $code = $LASTEXITCODE
    if ($null -eq $code) { $code = 1 }

    if ($code -eq 0) {
        Write-Host "Stopped cleanly." -ForegroundColor Green
        break
    }

    $failCount = $failCount + 1
    if ($code -eq 42) {
        Write-Host "Source updated - restarting in 1s..." -ForegroundColor Yellow
        $failCount = 0
        Start-Sleep -Seconds 1
    } else {
        $backoff = [Math]::Min(15, 2 + $failCount)
        Write-Host "Exited $code - restarting in ${backoff}s..." -ForegroundColor Yellow
        Start-Sleep -Seconds $backoff
    }
}
