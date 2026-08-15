# ETHER host recovery — one shot
#
# Use when Grok reports stale heartbeat + pending jobs not consumed.
# This is the ONLY manual recovery step. After it succeeds, leave the
# window open; start_ether_host.ps1 keeps the process alive forever.
#
#   cd C:\Users\Otcde\ETHER
#   powershell -ExecutionPolicy Bypass -File .\scripts\recover_host.ps1
#
# Equivalent short form (from anywhere if path known):
#   powershell -ExecutionPolicy Bypass -File C:\Users\Otcde\ETHER\scripts\recover_host.ps1

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir

if (-not (Test-Path (Join-Path $Root "core"))) {
    # Fallback: known host path
    $Root = "C:\Users\Otcde\ETHER"
}
if (-not (Test-Path (Join-Path $Root "core"))) {
    Write-Error "ETHER root not found. Expected core/ under $Root"
    exit 1
}

Set-Location -LiteralPath $Root
Write-Host "========================================" -ForegroundColor Green
Write-Host " ETHER HOST RECOVERY" -ForegroundColor Green
Write-Host " root=$Root" -ForegroundColor DarkGray
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

# Process-scoped execution policy so we do not require admin
try {
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force -ErrorAction SilentlyContinue
} catch {}

$Launcher = Join-Path $Root "scripts\start_ether_host.ps1"
if (-not (Test-Path -LiteralPath $Launcher)) {
    Write-Error "Missing $Launcher — git pull first?"
    exit 1
}

# -Recover: kill stale host python, hard-reset origin/main, then enter the
# self-healing start loop (exit 0 = stop, 42 = fast reload, other = backoff).
& powershell -NoProfile -ExecutionPolicy Bypass -File $Launcher -Recover
exit $LASTEXITCODE
