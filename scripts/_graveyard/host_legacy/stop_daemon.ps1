# Stop all @ETHER daemon processes (safe, non-fatal)
$ErrorActionPreference = "SilentlyContinue"
$Root = Split-Path (Split-Path $MyInvocation.MyCommand.Path -Parent) -Parent
if (-not $Root) { $Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path }

Write-Host "[stop] cleaning @ETHER processes in $Root"

# Scheduled task
try {
  $task = Get-ScheduledTask -TaskName "ETHER-Daemon" -ErrorAction SilentlyContinue
  if ($task) {
    Stop-ScheduledTask -TaskName "ETHER-Daemon" -ErrorAction SilentlyContinue
    Write-Host "[stop] scheduled task stopped"
  }
} catch {}

# PID file
$PidFile = Join-Path $Root "memory\daemon\daemon.pid"
if (Test-Path -LiteralPath $PidFile) {
  $raw = (Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
  if ($raw -match '^\s*(\d+)\s*$') {
    $oldPid = [int]$Matches[1]
    if ($oldPid -gt 0) {
      Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue
      Write-Host "[stop] killed pid $oldPid"
    }
  }
  Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
}

# Any python whose command line mentions our scripts
try {
  Get-CimInstance Win32_Process |
    Where-Object { $_.Name -match 'python' -and $_.CommandLine -and (
      $_.CommandLine -match 'ether_daemon\.py' -or
      $_.CommandLine -match 'desktop_runtime\.py' -or
      $_.CommandLine -match 'cli\.main.*flywheel' -or
      ($_.CommandLine -match 'uvicorn' -and $_.CommandLine -match 'dashboard\.app')
    )} |
    ForEach-Object {
      Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
      Write-Host "[stop] killed pid $($_.ProcessId)"
    }
} catch {
  Write-Host "[stop] process scan skipped: $_"
}

Write-Host "[stop] done"
