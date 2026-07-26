# Keep GitHub self-hosted runner alive on Windows.
# Official win-x64 zip (2.336+) no longer ships svc.cmd - use Scheduled Task + run.cmd.
#
#   powershell -ExecutionPolicy Bypass -File C:\Users\Otcde\ETHER\scripts\install_runner_service.ps1

$ErrorActionPreference = "Stop"
$RunnerDir = if ($env:ETHER_RUNNER_DIR) { $env:ETHER_RUNNER_DIR } else { "C:\actions-runner" }
$RunnerVersion = if ($env:ETHER_RUNNER_VERSION) { $env:ETHER_RUNNER_VERSION } else { "2.336.0" }
$ZipName = "actions-runner-win-x64-$RunnerVersion.zip"
$ZipUrl = "https://github.com/actions/runner/releases/download/v$RunnerVersion/$ZipName"
$ExpectedSha = "D59123A43003E357B0805B5D0F611D0BD2F65AB67D51BD070DD4E7A0F685C162"
$TaskRun = "ETHER-Runner"
$TaskWatch = "ETHER-RunnerWatch"
# Task Scheduler rejects [TimeSpan]::MaxValue (P99999999D...). Use ~10 years.
$RepeatFor = New-TimeSpan -Days 3650

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

function Test-RunnerBinaries {
  return (Test-Path -LiteralPath (Join-Path $RunnerDir "config.cmd")) -and
         (Test-Path -LiteralPath (Join-Path $RunnerDir "run.cmd"))
}

function Repair-RunnerPackage {
  Write-Step "downloading $ZipUrl"
  $zipPath = Join-Path $env:TEMP $ZipName
  if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
  Invoke-WebRequest -Uri $ZipUrl -OutFile $zipPath -UseBasicParsing
  $hash = (Get-FileHash -Path $zipPath -Algorithm SHA256).Hash.ToUpper()
  Write-Step "sha256=$hash"
  if ($hash -ne $ExpectedSha) { throw "checksum mismatch got=$hash expected=$ExpectedSha" }

  $tmpExtract = Join-Path $env:TEMP "ether-runner-extract-$(Get-Random)"
  if (Test-Path $tmpExtract) { Remove-Item $tmpExtract -Recurse -Force }
  New-Item -ItemType Directory -Path $tmpExtract | Out-Null
  Expand-Archive -Path $zipPath -DestinationPath $tmpExtract -Force

  $runFound = Get-ChildItem -Path $tmpExtract -Filter "run.cmd" -Recurse | Select-Object -First 1
  if (-not $runFound) { throw "run.cmd not in zip" }
  $srcRoot = $runFound.Directory.FullName
  Write-Step "package root=$srcRoot"

  $preserve = @(".runner", ".credentials", ".credentials_rsaparams", ".service", ".path")
  $backup = Join-Path $env:TEMP "ether-runner-bak-$(Get-Random)"
  New-Item -ItemType Directory -Path $backup -Force | Out-Null
  foreach ($f in $preserve) {
    $p = Join-Path $RunnerDir $f
    if (Test-Path -LiteralPath $p) { Copy-Item $p (Join-Path $backup $f) -Force }
  }

  Get-ChildItem -LiteralPath $srcRoot -Force | ForEach-Object {
    Copy-Item $_.FullName (Join-Path $RunnerDir $_.Name) -Recurse -Force
  }
  foreach ($f in $preserve) {
    $src = Join-Path $backup $f
    if (Test-Path $src) { Copy-Item $src (Join-Path $RunnerDir $f) -Force }
  }
  Remove-Item $tmpExtract, $backup, $zipPath -Recurse -Force -ErrorAction SilentlyContinue
  Write-Step "binaries repaired"
}

if (-not (Test-RunnerBinaries)) {
  Write-Step "binaries incomplete - repairing"
  Repair-RunnerPackage
}

if (-not (Test-Path -LiteralPath (Join-Path $RunnerDir ".runner"))) {
  throw @"
Runner binaries OK but not registered.
Token: https://github.com/OxCryptobot/-ETHER/settings/actions/runners/new
  cd $RunnerDir
  .\config.cmd --url https://github.com/OxCryptobot/-ETHER --token TOKEN --name ether-windows-$env:COMPUTERNAME --labels self-hosted,Windows,ETHER,X64 --work _work --unattended --replace
  powershell -ExecutionPolicy Bypass -File C:\Users\Otcde\ETHER\scripts\install_runner_service.ps1
"@
}

if (Test-Path -LiteralPath (Join-Path $RunnerDir "svc.cmd")) {
  Write-Step "svc.cmd found - using official service helper"
  try { & .\svc.cmd install } catch { Write-Step "svc install: $_" }
  try { & .\svc.cmd start } catch { Write-Step "svc start: $_" }
}

$psExe = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$cmdExe = "$env:SystemRoot\System32\cmd.exe"

$runArg = "/c cd /d `"$RunnerDir`" && run.cmd"
try { Unregister-ScheduledTask -TaskName $TaskRun -Confirm:$false -ErrorAction SilentlyContinue } catch {}
$actionRun = New-ScheduledTaskAction -Execute $cmdExe -Argument $runArg -WorkingDirectory $RunnerDir
$triggerLogon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settingsRun = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
  -ExecutionTimeLimit ([TimeSpan]::Zero) `
  -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName $TaskRun -Action $actionRun -Trigger $triggerLogon -Settings $settingsRun -Principal $principal -Description "ETHER GitHub Actions runner (run.cmd)" -Force | Out-Null
Write-Step "registered task $TaskRun (AtLogOn + restart)"

$watchScript = @"
`$ErrorActionPreference = 'SilentlyContinue'
if (-not (Get-Process -Name 'Runner.Listener' -ErrorAction SilentlyContinue)) {
  Start-ScheduledTask -TaskName '$TaskRun'
}
"@
$watchPath = Join-Path $RunnerDir "ether-runner-watch.ps1"
Set-Content -LiteralPath $watchPath -Value $watchScript -Encoding UTF8

try { Unregister-ScheduledTask -TaskName $TaskWatch -Confirm:$false -ErrorAction SilentlyContinue } catch {}
$actionWatch = New-ScheduledTaskAction -Execute $psExe -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$watchPath`""
$triggerWatch = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration $RepeatFor
$settingsWatch = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
Register-ScheduledTask -TaskName $TaskWatch -Action $actionWatch -Trigger $triggerWatch -Settings $settingsWatch -Principal $principal -Description "ETHER runner watchdog - restart if Listener dead" -Force | Out-Null
Write-Step "registered task $TaskWatch (every 5 min)"

Write-Step "starting $TaskRun now"
Start-ScheduledTask -TaskName $TaskRun
Start-Sleep -Seconds 6
$alive = [bool](Get-Process -Name "Runner.Listener" -ErrorAction SilentlyContinue)
if ($alive) {
  Write-Step "OK - Runner.Listener is running. You can close any run.cmd window."
} else {
  Write-Step "WARN - Listener not seen yet; watchdog will retry every 5 min"
  Write-Step "Manual: Start-ScheduledTask -TaskName $TaskRun"
}
Write-Host "Verify Idle: https://github.com/OxCryptobot/-ETHER/settings/actions/runners"
