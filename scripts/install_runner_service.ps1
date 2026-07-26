# Install self-hosted runner as a Windows SERVICE.
# Repairs incomplete packages (missing svc.cmd) by re-downloading the official zip.
#
#   powershell -ExecutionPolicy Bypass -File C:\Users\Otcde\ETHER\scripts\install_runner_service.ps1

$ErrorActionPreference = "Stop"
$RunnerDir = if ($env:ETHER_RUNNER_DIR) { $env:ETHER_RUNNER_DIR } else { "C:\actions-runner" }
$RunnerVersion = if ($env:ETHER_RUNNER_VERSION) { $env:ETHER_RUNNER_VERSION } else { "2.336.0" }
$ZipName = "actions-runner-win-x64-$RunnerVersion.zip"
$ZipUrl = "https://github.com/actions/runner/releases/download/v$RunnerVersion/$ZipName"
$ExpectedSha = "D59123A43003E357B0805B5D0F611D0BD2F65AB67D51BD070DD4E7A0F685C162"

function Write-Step([string]$m) { Write-Host "[runner] $m" }

if (-not (Test-Path -LiteralPath $RunnerDir)) {
  New-Item -ItemType Directory -Path $RunnerDir -Force | Out-Null
}
Set-Location -LiteralPath $RunnerDir
Write-Step "dir=$RunnerDir"

# Stop interactive listener if running
Get-Process -Name "Runner.Listener" -ErrorAction SilentlyContinue | ForEach-Object {
  Write-Step "stopping interactive Listener pid=$($_.Id)"
  try { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue } catch {}
}
Start-Sleep -Seconds 2

function Test-RunnerComplete {
  return (Test-Path -LiteralPath (Join-Path $RunnerDir "config.cmd")) -and
         (Test-Path -LiteralPath (Join-Path $RunnerDir "run.cmd")) -and
         (Test-Path -LiteralPath (Join-Path $RunnerDir "svc.cmd"))
}

if (-not (Test-RunnerComplete)) {
  Write-Step "package incomplete - downloading $ZipName"
  $zipPath = Join-Path $RunnerDir $ZipName
  # Preserve registration files across repair
  $preserve = @(".runner", ".credentials", ".credentials_rsaparams", ".service", ".path")
  $backup = Join-Path $env:TEMP "ether-runner-bak"
  if (Test-Path $backup) { Remove-Item $backup -Recurse -Force -ErrorAction SilentlyContinue }
  New-Item -ItemType Directory -Path $backup -Force | Out-Null
  foreach ($f in $preserve) {
    $p = Join-Path $RunnerDir $f
    if (Test-Path -LiteralPath $p) {
      Copy-Item -LiteralPath $p -Destination (Join-Path $backup $f) -Force -ErrorAction SilentlyContinue
    }
  }

  Invoke-WebRequest -Uri $ZipUrl -OutFile $zipPath
  $hash = (Get-FileHash -Path $zipPath -Algorithm SHA256).Hash.ToUpper()
  if ($hash -ne $ExpectedSha) {
    throw "checksum mismatch for $ZipName got=$hash expected=$ExpectedSha"
  }

  # Extract without wiping registration
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  $tmpExtract = Join-Path $env:TEMP "ether-runner-extract"
  if (Test-Path $tmpExtract) { Remove-Item $tmpExtract -Recurse -Force }
  New-Item -ItemType Directory -Path $tmpExtract | Out-Null
  [System.IO.Compression.ZipFile]::ExtractToDirectory($zipPath, $tmpExtract)
  Copy-Item -Path (Join-Path $tmpExtract "*") -Destination $RunnerDir -Recurse -Force
  Remove-Item $tmpExtract -Recurse -Force -ErrorAction SilentlyContinue
  Remove-Item $zipPath -Force -ErrorAction SilentlyContinue

  foreach ($f in $preserve) {
    $src = Join-Path $backup $f
    if (Test-Path -LiteralPath $src) {
      Copy-Item -LiteralPath $src -Destination (Join-Path $RunnerDir $f) -Force
    }
  }
  Remove-Item $backup -Recurse -Force -ErrorAction SilentlyContinue

  if (-not (Test-RunnerComplete)) {
    throw "repair failed - svc.cmd still missing in $RunnerDir"
  }
  Write-Step "package repaired"
}

# Must be configured against the repo
if (-not (Test-Path -LiteralPath (Join-Path $RunnerDir ".runner"))) {
  throw "Runner binaries OK but not registered. Get a fresh token from GitHub Actions runners page and run:`n  cd $RunnerDir`n  .\config.cmd --url https://github.com/OxCryptobot/-ETHER --token TOKEN --name ether-windows-$env:COMPUTERNAME --labels self-hosted,Windows,ETHER,X64 --work _work --unattended --replace"
}

if (-not (Test-Path ".\svc.cmd")) {
  throw "svc.cmd still missing after repair"
}

Write-Step "svc install"
& .\svc.cmd install
Write-Step "svc start"
& .\svc.cmd start
try { & .\svc.cmd status } catch {}

# Watchdog scheduled task every 10 min
$taskName = "ETHER-RunnerService"
$ps = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$arg = "-NoProfile -Command `"Set-Location '$RunnerDir'; if (Test-Path .\svc.cmd) { .\svc.cmd start 2>`$null }`""
try { Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue } catch {}
$action = New-ScheduledTaskAction -Execute $ps -Argument $arg
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 10) -RepetitionDuration ([TimeSpan]::MaxValue)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Restart ETHER GitHub runner service if stopped" -Force | Out-Null

Write-Step "OK - service installed. You can close run.cmd."
Write-Host "Verify: https://github.com/OxCryptobot/-ETHER/settings/actions/runners"
