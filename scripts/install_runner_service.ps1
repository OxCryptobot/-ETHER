# Install self-hosted runner as a Windows SERVICE so closing run.cmd does not kill autonomy.
# Run from elevated PowerShell if svc install fails without admin.
#
#   powershell -ExecutionPolicy Bypass -File C:\Users\Otcde\ETHER\scripts\install_runner_service.ps1

$ErrorActionPreference = "Stop"
$RunnerDir = if ($env:ETHER_RUNNER_DIR) { $env:ETHER_RUNNER_DIR } else { "C:\actions-runner" }

if (-not (Test-Path -LiteralPath (Join-Path $RunnerDir "config.cmd"))) {
  throw "Runner not configured at $RunnerDir - run GitHub config.cmd first"
}

Set-Location -LiteralPath $RunnerDir
Write-Host "[runner] dir=$RunnerDir"

# Stop interactive run if present (best-effort)
Get-Process -Name "Runner.Listener" -ErrorAction SilentlyContinue | ForEach-Object {
  Write-Host "[runner] stopping interactive Listener pid=$($_.Id)"
  try { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue } catch {}
}
Start-Sleep -Seconds 2

if (Test-Path ".\svc.cmd") {
  Write-Host "[runner] svc install"
  & .\svc.cmd install
  Write-Host "[runner] svc start"
  & .\svc.cmd start
  & .\svc.cmd status
} else {
  throw "svc.cmd missing - incomplete runner package"
}

# Scheduled safety net: start service every 10 min if stopped
$taskName = "ETHER-RunnerService"
$ps = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$arg = "-NoProfile -Command `"if ((Get-Service actions.runner.* -ErrorAction SilentlyContinue | Where-Object { `$_.Status -ne 'Running' })) { Set-Location '$RunnerDir'; .\svc.cmd start }`""
try {
  Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
} catch {}
$action = New-ScheduledTaskAction -Execute $ps -Argument $arg
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 10) -RepetitionDuration ([TimeSpan]::MaxValue)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Restart ETHER GitHub runner service if stopped" -Force | Out-Null

Write-Host "OK - runner service + ETHER-RunnerService watchdog task registered"
Write-Host "You can close any run.cmd window."
