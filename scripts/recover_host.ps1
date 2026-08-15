# ETHER host recovery -- thin wrapper
#
# All real work lives in start_ether_host.ps1 (single process, boot probe,
# self-healing loop). This file exists only so older docs/commands still work.
#
#   cd C:\Users\Otcde\ETHER
#   powershell -ExecutionPolicy Bypass -File .\scripts\recover_host.ps1
#   powershell -ExecutionPolicy Bypass -File .\scripts\recover_host.ps1 -Hard
#
# Prefer calling start_ether_host.ps1 -Hard directly.

param(
    [switch]$Hard
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

$ScriptDir = $null
try { $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path } catch { $ScriptDir = $PSScriptRoot }
if (-not $ScriptDir) { $ScriptDir = (Get-Location).Path }
$Root = Split-Path -Parent $ScriptDir
if (-not (Test-Path (Join-Path $Root "core"))) { $Root = "C:\Users\Otcde\ETHER" }
if (-not (Test-Path (Join-Path $Root "core"))) {
    Write-Host "FAIL  ETHER root not found" -ForegroundColor Red
    exit 1
}
Set-Location -LiteralPath $Root

$Launcher = Join-Path $Root "scripts\start_ether_host.ps1"
if (-not (Test-Path -LiteralPath $Launcher)) {
    Write-Host "FAIL  Missing $Launcher" -ForegroundColor Red
    exit 1
}

Write-Host "recover_host -> start_ether_host.ps1 (single process)" -ForegroundColor Cyan

# Call in the SAME process. No nested powershell. Never silent death.
if ($Hard) {
    & $Launcher -Recover -Hard
} else {
    & $Launcher -Recover
}
exit $LASTEXITCODE
