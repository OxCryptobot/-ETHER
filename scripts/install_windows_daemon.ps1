# Install @ETHER as a logon Scheduled Task (background daemon).
# Runs without this chat. Survives closing the browser.

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Py = Join-Path $Root ".venv\Scripts\python.exe"
$Daemon = Join-Path $Root "scripts\ether_daemon.py"
$TaskName = "ETHER-Daemon"

if (-not (Test-Path $Py)) {
  Write-Error "Missing venv python at $Py - run scripts\bootstrap.ps1 first"
}
if (-not (Test-Path $Daemon)) {
  Write-Error "Missing $Daemon"
}

# Remove old task if present
schtasks /Delete /TN $TaskName /F 2>$null | Out-Null

# At logon, highest available privileges for current user
$tr = "`"$Py`" `"$Daemon`""
schtasks /Create /TN $TaskName /SC ONLOGON /RL LIMITED /TR $tr /F
if ($LASTEXITCODE -ne 0) {
  Write-Error "schtasks create failed"
}

Write-Host ""
Write-Host "OK - Windows Scheduled Task installed: $TaskName" -ForegroundColor Green
Write-Host "  Root   : $Root"
Write-Host "  Python : $Py"
Write-Host "  Script : $Daemon"
Write-Host ""
Write-Host "Start now:"
Write-Host "  schtasks /Run /TN $TaskName"
Write-Host "Stop:"
Write-Host "  schtasks /End /TN $TaskName"
Write-Host "Remove:"
Write-Host "  schtasks /Delete /TN $TaskName /F"
Write-Host ""
Write-Host "Logs: $Root\memory\daemon\daemon.log"
Write-Host "Heartbeat: $Root\memory\daemon\heartbeat.txt"
