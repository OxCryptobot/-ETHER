# Install @ETHER as a logon Scheduled Task (background daemon).
# Tolerates missing prior task. ASCII-only for Windows PowerShell 5.x.

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Py = Join-Path $Root ".venv\Scripts\python.exe"
$Daemon = Join-Path $Root "scripts\ether_daemon.py"
$TaskName = "ETHER-Daemon"

if (-not (Test-Path -LiteralPath $Py)) {
    Write-Error "Missing venv python at $Py - create venv first: python -m venv .venv && .\.venv\Scripts\python.exe -m pip install -e .[dev]"
}
if (-not (Test-Path -LiteralPath $Daemon)) {
    Write-Error "Missing $Daemon - git pull origin main first"
}

# Remove existing task if present (do NOT fail if absent)
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -ne $existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed old task: $TaskName"
}

# Action: venv python runs ether_daemon.py; WorkingDirectory = repo root
$arg = "`"$Daemon`""
$action = New-ScheduledTaskAction -Execute $Py -Argument $arg -WorkingDirectory $Root

# Trigger: at logon for current user
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

# Settings: allow start on battery, restart on fail, no time limit
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0)

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "@ETHER local daemon: flywheel + batch queue + optional dashboard" `
    -Force | Out-Null

Write-Host ""
Write-Host "OK - Scheduled Task installed: $TaskName" -ForegroundColor Green
Write-Host "  Root   : $Root"
Write-Host "  Python : $Py"
Write-Host "  Script : $Daemon"
Write-Host ""
Write-Host "Start now:"
Write-Host "  Start-ScheduledTask -TaskName $TaskName"
Write-Host "  # or: schtasks /Run /TN $TaskName"
Write-Host "Stop:"
Write-Host "  Stop-ScheduledTask -TaskName $TaskName"
Write-Host "Remove:"
Write-Host "  Unregister-ScheduledTask -TaskName $TaskName -Confirm:`$false"
Write-Host ""
Write-Host "Logs:      $Root\memory\daemon\daemon.log"
Write-Host "Heartbeat: $Root\memory\daemon\heartbeat.txt"
Write-Host ""

# Verify registration
$t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -eq $t) {
    Write-Error "Task registered but Get-ScheduledTask cannot see it. Try elevated PowerShell."
} else {
    Write-Host "Verified: state=$($t.State)"
}
