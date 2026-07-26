# Stop all @ETHER daemon / flywheel / dashboard processes — safe cleanup
$ErrorActionPreference = "Continue"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PidFile = Join-Path $Root "memory\daemon\daemon.pid"

Write-Host "Stopping @ETHER processes..."

# Stop scheduled task if present
$task = Get-ScheduledTask -TaskName "ETHER-Daemon" -ErrorAction SilentlyContinue
if ($null -ne $task) {
    Stop-ScheduledTask -TaskName "ETHER-Daemon" -ErrorAction SilentlyContinue
    Write-Host "  stopped Scheduled Task ETHER-Daemon"
}

# Kill by PID file
if (Test-Path $PidFile) {
    $pidText = (Get-Content $PidFile -Raw).Trim()
    if ($pidText -match '^\d+$') {
        $procId = [int]$pidText
        try {
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
            Write-Host "  killed pid $procId from daemon.pid"
        } catch {}
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

# Kill matching python processes for this repo (best-effort)
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object {
    $_.CommandLine -and (
      $_.CommandLine -like "*ether_daemon.py*" -or
      $_.CommandLine -like "*desktop_runtime.py*" -or
      $_.CommandLine -like "*cli.main*flywheel*" -or
      ($_.CommandLine -like "*uvicorn*" -and $_.CommandLine -like "*dashboard.app*")
    )
  } |
  ForEach-Object {
    try {
      Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
      Write-Host "  killed pid $($_.ProcessId)"
    } catch {}
  }

Write-Host "Done. You can start ONE process with:"
Write-Host "  powershell -ExecutionPolicy Bypass -File .\scripts\start_daemon.ps1 -Foreground"
