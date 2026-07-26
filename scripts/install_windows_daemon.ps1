# Optional: register logon Scheduled Task. Core autonomy does NOT require this.
$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Py = Join-Path $Root ".venv\Scripts\python.exe"
$Daemon = Join-Path $Root "scripts\ether_daemon.py"
$TaskName = "ETHER-Daemon"

if (-not (Test-Path -LiteralPath $Py)) { Write-Error "Missing $Py" }
if (-not (Test-Path -LiteralPath $Daemon)) { Write-Error "Missing $Daemon" }

try {
  $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
  if ($existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
  }
} catch {}

$action = New-ScheduledTaskAction -Execute $Py -Argument "`"$Daemon`"" -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "ETHER daemon" -Force | Out-Null

Write-Host "OK - task $TaskName registered"
Get-ScheduledTask -TaskName $TaskName | Format-List TaskName, State
