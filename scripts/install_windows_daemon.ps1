# Registers always-on autonomy on Windows:
#   ETHER-Daemon  - main process at logon
#   ETHER-Ensure  - every 5 min: start daemon if dead / heartbeat stale
#
#   powershell -ExecutionPolicy Bypass -File .\scripts\install_windows_daemon.ps1

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Py = Join-Path $Root ".venv\Scripts\python.exe"
$PyW = Join-Path $Root ".venv\Scripts\pythonw.exe"
$DaemonExe = if (Test-Path -LiteralPath $PyW) { $PyW } else { $Py }
$Daemon = Join-Path $Root "scripts\ether_daemon.py"
$Ensure = Join-Path $Root "scripts\ensure_daemon.ps1"
$Ps = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
# Task Scheduler rejects [TimeSpan]::MaxValue
$RepeatFor = New-TimeSpan -Days 3650

if (-not (Test-Path -LiteralPath $Py)) {
  Write-Host "[venv] creating"
  Set-Location -LiteralPath $Root
  python -m venv .venv
  & $Py -m pip install -U pip
  & $Py -m pip install -e ".[dev]"
}
if (-not (Test-Path -LiteralPath $Daemon)) { Write-Error "Missing $Daemon" }
if (-not (Test-Path -LiteralPath $Ensure)) { Write-Error "Missing $Ensure" }

function Register-EtherTask {
  param(
    [string]$Name,
    [string]$Execute,
    [string]$Argument,
    [object]$Trigger,
    [string]$Description
  )
  try {
    $existing = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
    if ($existing) {
      Unregister-ScheduledTask -TaskName $Name -Confirm:$false -ErrorAction SilentlyContinue
    }
  } catch {}

  $action = New-ScheduledTaskAction -Execute $Execute -Argument $Argument -WorkingDirectory $Root
  $settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -Hidden
  $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
  Register-ScheduledTask -TaskName $Name -Action $action -Trigger $Trigger -Settings $settings -Principal $principal -Description $Description -Force | Out-Null
  Write-Host "OK registered $Name"
}

$tLogon = New-ScheduledTaskTrigger -AtLogOn
Register-EtherTask -Name "ETHER-Daemon" `
  -Execute $DaemonExe `
  -Argument "`"$Daemon`"" `
  -Trigger $tLogon `
  -Description "@ETHER autonomous daemon (flywheel+batch+recovery+dashboard) — hidden, no console"

$tEnsure = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration $RepeatFor
Register-EtherTask -Name "ETHER-Ensure" `
  -Execute $Ps `
  -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Ensure`"" `
  -Trigger $tEnsure `
  -Description "@ETHER ensure daemon alive (heartbeat watchdog) — hidden, no console"

try { Start-ScheduledTask -TaskName "ETHER-Daemon" -ErrorAction SilentlyContinue } catch {}
try { Start-ScheduledTask -TaskName "ETHER-Ensure" -ErrorAction SilentlyContinue } catch {}

Start-Process -FilePath $Ps -ArgumentList "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Ensure`"" -WorkingDirectory $Root -WindowStyle Hidden

Write-Host ""
Write-Host "Autonomy registered. Tasks: ETHER-Daemon + ETHER-Ensure"
Get-ScheduledTask -TaskName "ETHER-Daemon","ETHER-Ensure" -ErrorAction SilentlyContinue | Format-Table TaskName, State
