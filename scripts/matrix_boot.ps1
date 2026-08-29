# Control Matrix hidden boot. No console window. Idempotent.
# Invoked by: Host button wake file, ETHER-Ensure, autonomy-host.yml, silent_boot.vbs
param(
    [switch]$SkipPull
)

$ErrorActionPreference = "Continue"

function Resolve-Root {
  if ($env:ETHER_ROOT -and (Test-Path -LiteralPath $env:ETHER_ROOT)) {
    return (Resolve-Path -LiteralPath $env:ETHER_ROOT).Path
  }
  foreach ($c in @("C:\Users\Otcde\ETHER", "C:\ETHER")) {
    if (Test-Path -LiteralPath $c) { return (Resolve-Path -LiteralPath $c).Path }
  }
  return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

$Root = Resolve-Root
$env:ETHER_ROOT = $Root
Set-Location -LiteralPath $Root
try { Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force } catch {}

$LogDir = Join-Path $Root "memory\daemon"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
$Log = Join-Path $LogDir "matrix_boot.log"
function Write-Boot([string]$m) {
  $line = "[{0}] {1}" -f (Get-Date).ToUniversalTime().ToString("o"), $m
  try { Add-Content -LiteralPath $Log -Value $line -Encoding UTF8 } catch {}
}

Write-Boot "root=$Root skipPull=$SkipPull"

if (-not $SkipPull) {
  Write-Boot "git fetch + reset origin/main"
  git fetch origin 2>&1 | Out-File -FilePath $Log -Append -Encoding UTF8
  git reset --hard origin/main 2>&1 | Out-File -FilePath $Log -Append -Encoding UTF8
}

$PyW = Join-Path $Root ".venv\Scripts\pythonw.exe"
$Py = Join-Path $Root ".venv\Scripts\python.exe"
$Daemon = Join-Path $Root "scripts\ether_daemon.py"
$Ensure = Join-Path $Root "scripts\ensure_daemon.ps1"
$Inst = Join-Path $Root "scripts\install_windows_daemon.ps1"
$Ps = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"

if (-not (Test-Path -LiteralPath $Py)) {
  Write-Boot "creating venv"
  python -m venv .venv
  & $Py -m pip install -U pip -q
  & $Py -m pip install -e ".[dev]" -q
}

if (Test-Path -LiteralPath $Ensure) {
  Write-Boot "ensure_daemon hidden"
  Start-Process -FilePath $Ps -ArgumentList "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Ensure`"" -WorkingDirectory $Root -WindowStyle Hidden
} elseif (Test-Path -LiteralPath $Daemon) {
  $exe = if (Test-Path -LiteralPath $PyW) { $PyW } else { $Py }
  Write-Boot "start daemon hidden via $exe"
  Start-Process -FilePath $exe -ArgumentList "`"$Daemon`"" -WorkingDirectory $Root -WindowStyle Hidden
}

if (Test-Path -LiteralPath $Inst) {
  Write-Boot "re-register hidden listener"
  Start-Process -FilePath $Ps -ArgumentList "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Inst`"" -WorkingDirectory $Root -WindowStyle Hidden
}

$wake = Join-Path $Root "artifacts\host\matrix_wake.json"
if (Test-Path -LiteralPath $wake) {
  try {
    $now = (Get-Date).ToUniversalTime().ToString("o")
    $body = @{
      schema = "ether_matrix_wake_v1"
      action = "boot"
      hidden = $true
      status = "consumed"
      consumed_at = $now
      source = "matrix_boot.ps1"
    } | ConvertTo-Json -Depth 4
    Set-Content -LiteralPath $wake -Value $body -Encoding UTF8
    Write-Boot "wake consumed"
  } catch {
    Write-Boot "wake consume failed"
  }
}

Write-Boot "done"
exit 0
