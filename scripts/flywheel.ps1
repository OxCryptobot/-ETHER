# @ETHER Agentic Flywheel — PowerShell launcher
# Push is BLOCKED unless audit approved AND confidence >= threshold.
# On failure the pipeline retries until max retries.
#
# Usage:
#   .\scripts\flywheel.ps1
#   .\scripts\flywheel.ps1 -Push
#   .\scripts\flywheel.ps1 -Push -MinConfidence 0.8 -MaxRetries 5

param(
    [switch]$Push,
    [double]$MinConfidence = 0.7,
    [int]$MaxRetries = 3,
    [int]$Loop = 0,
    [switch]$NoDoctor,
    [string]$Objective = ""
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
    . .\.venv\Scripts\Activate.ps1
}

$argsList = @(
    "scripts/flywheel.py",
    "--min-confidence", "$MinConfidence",
    "--max-retries", "$MaxRetries"
)
if ($Push) { $argsList += "--push" }
if ($Loop -gt 0) { $argsList += @("--loop", "$Loop") }
if ($NoDoctor) { $argsList += "--no-doctor" }
if ($Objective -ne "") { $argsList += @("--objective", $Objective) }

Write-Host "@ETHER agentic flywheel (min conf=$MinConfidence, retries=$MaxRetries)" -ForegroundColor Cyan
python @argsList
exit $LASTEXITCODE
