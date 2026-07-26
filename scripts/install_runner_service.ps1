# Install self-hosted runner as a Windows SERVICE.
# Repairs incomplete packages by re-downloading and locating svc.cmd recursively.
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

Get-Process -Name "Runner.Listener" -ErrorAction SilentlyContinue | ForEach-Object {
  Write-Step "stopping Listener pid=$($_.Id)"
  try { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue } catch {}
}
Start-Sleep -Seconds 2

function Test-RunnerComplete {
  $svc = Join-Path $RunnerDir "svc.cmd"
  $cfg = Join-Path $RunnerDir "config.cmd"
  $run = Join-Path $RunnerDir "run.cmd"
  return (Test-Path -LiteralPath $svc) -and (Test-Path -LiteralPath $cfg) -and (Test-Path -LiteralPath $run)
}

function Repair-RunnerPackage {
  Write-Step "downloading $ZipUrl"
  $zipPath = Join-Path $env:TEMP $ZipName
  if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
  Invoke-WebRequest -Uri $ZipUrl -OutFile $zipPath -UseBasicParsing
  $hash = (Get-FileHash -Path $zipPath -Algorithm SHA256).Hash.ToUpper()
  Write-Step "sha256=$hash"
  if ($hash -ne $ExpectedSha) {
    throw "checksum mismatch got=$hash expected=$ExpectedSha"
  }

  $tmpExtract = Join-Path $env:TEMP "ether-runner-extract-$(Get-Random)"
  if (Test-Path $tmpExtract) { Remove-Item $tmpExtract -Recurse -Force }
  New-Item -ItemType Directory -Path $tmpExtract | Out-Null
  Write-Step "extracting to $tmpExtract"
  Expand-Archive -Path $zipPath -DestinationPath $tmpExtract -Force

  # Find real root (svc.cmd may be nested one level)
  $svcFound = Get-ChildItem -Path $tmpExtract -Filter "svc.cmd" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $svcFound) {
    Write-Step "extracted tree:"
    Get-ChildItem -Path $tmpExtract -Recurse -Name | Select-Object -First 40 | ForEach-Object { Write-Host "  $_" }
    throw "svc.cmd not inside downloaded zip - blocked or wrong asset"
  }
  $srcRoot = $svcFound.Directory.FullName
  Write-Step "package root=$srcRoot"

  # Preserve registration
  $preserve = @(".runner", ".credentials", ".credentials_rsaparams", ".service", ".path")
  $backup = Join-Path $env:TEMP "ether-runner-bak-$(Get-Random)"
  New-Item -ItemType Directory -Path $backup -Force | Out-Null
  foreach ($f in $preserve) {
    $p = Join-Path $RunnerDir $f
    if (Test-Path -LiteralPath $p) {
      Copy-Item -LiteralPath $p -Destination (Join-Path $backup $f) -Force
    }
  }

  Write-Step "copying binaries into $RunnerDir"
  Get-ChildItem -LiteralPath $srcRoot -Force | ForEach-Object {
    $dest = Join-Path $RunnerDir $_.Name
    if ($_.PSIsContainer) {
      Copy-Item -LiteralPath $_.FullName -Destination $dest -Recurse -Force
    } else {
      Copy-Item -LiteralPath $_.FullName -Destination $dest -Force
    }
  }

  foreach ($f in $preserve) {
    $src = Join-Path $backup $f
    if (Test-Path -LiteralPath $src) {
      Copy-Item -LiteralPath $src -Destination (Join-Path $RunnerDir $f) -Force
    }
  }

  Remove-Item $tmpExtract -Recurse -Force -ErrorAction SilentlyContinue
  Remove-Item $backup -Recurse -Force -ErrorAction SilentlyContinue
  Remove-Item $zipPath -Force -ErrorAction SilentlyContinue

  if (-not (Test-Path -LiteralPath (Join-Path $RunnerDir "svc.cmd"))) {
    Write-Step "dir listing after copy:"
    Get-ChildItem -LiteralPath $RunnerDir -Name | Select-Object -First 30 | ForEach-Object { Write-Host "  $_" }
    throw "svc.cmd still missing after copy"
  }
  Write-Step "package OK (svc.cmd present)"
}

if (-not (Test-RunnerComplete)) {
  Write-Step "package incomplete - repairing"
  Repair-RunnerPackage
}

if (-not (Test-Path -LiteralPath (Join-Path $RunnerDir ".runner"))) {
  throw @"
Runner binaries OK but not registered.
Get a fresh token: https://github.com/OxCryptobot/-ETHER/settings/actions/runners/new
Then:
  cd $RunnerDir
  .\config.cmd --url https://github.com/OxCryptobot/-ETHER --token TOKEN --name ether-windows-$env:COMPUTERNAME --labels self-hosted,Windows,ETHER,X64 --work _work --unattended --replace
  powershell -ExecutionPolicy Bypass -File C:\Users\Otcde\ETHER\scripts\install_runner_service.ps1
"@
}

Write-Step "svc install"
& .\svc.cmd install
Write-Step "svc start"
& .\svc.cmd start
try { & .\svc.cmd status } catch { Write-Step "status: $_" }

$taskName = "ETHER-RunnerService"
$psExe = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$arg = "-NoProfile -Command `"Set-Location '$RunnerDir'; if (Test-Path .\svc.cmd) { .\svc.cmd start 2>`$null }`""
try { Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue } catch {}
$action = New-ScheduledTaskAction -Execute $psExe -Argument $arg
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 10) -RepetitionDuration ([TimeSpan]::MaxValue)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Restart ETHER GitHub runner service if stopped" -Force | Out-Null

Write-Step "OK - service installed. You can close run.cmd."
Write-Host "Verify: https://github.com/OxCryptobot/-ETHER/settings/actions/runners"
