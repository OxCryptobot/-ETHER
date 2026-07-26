# One-time bridge: GitHub Actions self-hosted runner on THIS Windows box.
# Supports win-x64 and win-arm64 (Snapdragon / Windows on ARM).
#
# Prereq: registration token from:
#   https://github.com/OxCryptobot/-ETHER/settings/actions/runners/new
# Labels: self-hosted, Windows, ETHER (+ arch label auto)
#
#   powershell -ExecutionPolicy Bypass -File .\scripts\install_self_hosted_runner.ps1 -Token XXX

param(
  [Parameter(Mandatory = $true)][string]$Token,
  [string]$RepoUrl = "https://github.com/OxCryptobot/-ETHER",
  [string]$RunnerDir = "$env:USERPROFILE\actions-runner-ether"
)

$ErrorActionPreference = "Stop"

# Detect architecture — Windows on ARM reports ARM64
$arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
if (-not $arch) {
  $arch = $env:PROCESSOR_ARCHITECTURE
}
$arch = $arch.ToUpperInvariant()

if ($arch -match "ARM64|AARCH64") {
  $runnerOsArch = "win-arm64"
  $archLabel = "ARM64"
} elseif ($arch -match "X86|X64|AMD64") {
  $runnerOsArch = "win-x64"
  $archLabel = "X64"
} else {
  Write-Host "Unknown arch '$arch' — defaulting to win-x64"
  $runnerOsArch = "win-x64"
  $archLabel = "X64"
}

Write-Host "========================================"
Write-Host " @ETHER self-hosted runner install"
Write-Host " arch=$arch → asset=$runnerOsArch"
Write-Host "========================================"

if (-not (Test-Path $RunnerDir)) {
  New-Item -ItemType Directory -Path $RunnerDir | Out-Null
}
Set-Location -LiteralPath $RunnerDir

if (-not (Test-Path ".\config.cmd")) {
  Write-Host "[download] actions runner ($runnerOsArch)"
  $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/actions/runner/releases/latest"
  $pattern = [regex]::Escape($runnerOsArch) + ".*\.zip$"
  $asset = $rel.assets | Where-Object { $_.name -match $pattern } | Select-Object -First 1
  if (-not $asset) {
    # fallback list names for debug
    $names = ($rel.assets | ForEach-Object { $_.name }) -join ", "
    throw "Could not find $runnerOsArch runner asset. Available: $names"
  }
  Write-Host "[download] $($asset.name)"
  Invoke-WebRequest -Uri $asset.browser_download_url -OutFile runner.zip
  Expand-Archive -Path runner.zip -DestinationPath . -Force
  Remove-Item runner.zip -Force
}

$labels = "self-hosted,Windows,ETHER,$archLabel"
Write-Host "[config] labels=$labels"
& .\config.cmd --url $RepoUrl --token $Token --name "ether-windows-$env:COMPUTERNAME" --labels $labels --work "_work" --unattended --replace

Write-Host "[service] install + start"
& .\svc.cmd install
& .\svc.cmd start

Write-Host ""
Write-Host "OK. Runner Idle at:"
Write-Host "  https://github.com/OxCryptobot/-ETHER/settings/actions/runners"
Write-Host "Asset: $runnerOsArch · labels: $labels"
