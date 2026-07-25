# @ETHER Flywheel — PowerShell launcher
# Usage:
#   .\scripts\flywheel.ps1
#   .\scripts\flywheel.ps1 -Push
#   .\scripts\flywheel.ps1 -Loop 300 -Push
#
# Run from repo root: C:\Users\Otcde\ETHER

param(
    [switch]$Push,
    [int]$Loop = 0,
    [switch]$NoDoctor
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
    . .\.venv\Scripts\Activate.ps1
}

$argsList = @("scripts/flywheel.py")
if ($Push) { $argsList += "--push" }
if ($Loop -gt 0) { $argsList += @("--loop", "$Loop") }
if ($NoDoctor) { $argsList += "--no-doctor" }

Write-Host "@ETHER flywheel starting..." -ForegroundColor Cyan
python @argsList
exit $LASTEXITCODE
