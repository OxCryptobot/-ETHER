# Remove host Scheduled Tasks that spawn visible PowerShell/cmd windows.
# These were keep-alive helpers for runner/daemon; they are optional and disruptive.
# Local autonomy should be started explicitly (ether daemon / ensure) when wanted,
# not via logon tasks that flash consoles every few minutes.
#
#   powershell -ExecutionPolicy Bypass -File .\scripts\remove_host_popups.ps1

$ErrorActionPreference = "Continue"

$TaskNames = @(
  "ETHER-Runner",
  "ETHER-RunnerWatch",
  "ETHER-RunnerService",
  "ETHER-Daemon",
  "ETHER-Ensure"
)

Write-Host "[remove] unregistering ETHER scheduled tasks that spawn console windows"

foreach ($name in $TaskNames) {
  try {
    $t = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($t) {
      Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
      Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
      Write-Host "  removed task $name"
    } else {
      Write-Host "  absent  $name"
    }
  } catch {
    Write-Host "  skip    $name : $_"
  }
}

# Stop interactive runner listener if it was started by those tasks
Get-Process -Name "Runner.Listener" -ErrorAction SilentlyContinue | ForEach-Object {
  Write-Host "  stopping Runner.Listener pid=$($_.Id)"
  try { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue } catch {}
}

# Optional: stop daemon python processes that were launched hidden from those tasks
# (do not kill arbitrary python - only if daemon.pid matches)
$Root = if ($env:ETHER_ROOT) { $env:ETHER_ROOT } else { "C:\Users\Otcde\ETHER" }
$PidFile = Join-Path $Root "memory\daemon\daemon.pid"
if (Test-Path -LiteralPath $PidFile) {
  try {
    $pidVal = [int]((Get-Content -LiteralPath $PidFile -Raw).Trim())
    if ($pidVal -gt 0) {
      $p = Get-Process -Id $pidVal -ErrorAction SilentlyContinue
      if ($p) {
        Write-Host "  stopping daemon pid=$pidVal"
        Stop-Process -Id $pidVal -Force -ErrorAction SilentlyContinue
      }
    }
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
  } catch {}
}

Write-Host "[remove] done"
Write-Host "Remaining ETHER* tasks:"
Get-ScheduledTask -ErrorAction SilentlyContinue |
  Where-Object { $_.TaskName -like "ETHER*" } |
  Format-Table TaskName, State -AutoSize
Write-Host "To run autonomy intentionally later: python -m cli.main doctor  then start daemon only when needed."
