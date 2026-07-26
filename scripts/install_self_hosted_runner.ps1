# One-time bridge: GitHub Actions self-hosted runner on THIS Windows box.
# After this, cloud-side agents can workflow_dispatch ensure/selftest/cycle on your host.
#
# Prereq: create a runner registration token at:
#   https://github.com/OxCryptobot/-ETHER/settings/actions/runners/new
# Labels required: self-hosted, Windows, ETHER
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\scripts\install_self_hosted_runner.ps1 -Token XXX

param(
  [Parameter(Mandatory = $true)][string]$Token,
  [string]$RepoUrl = "https://github.com/OxCryptobot/-ETHER",
  [string]$RunnerDir = "$env:USERPROFILE\actions-runner-ether"
)

$ErrorActionPreference = "Stop"

Write-Host "========================================"
Write-Host " @ETHER self-hosted runner install"
Write-Host " This is the control-plane bridge."
Write-Host "========================================"

if (-not (Test-Path $RunnerDir)) {
  New-Item -ItemType Directory -Path $RunnerDir | Out-Null
}
Set-Location -LiteralPath $RunnerDir

# Download latest runner if missing
if (-not (Test-Path ".\config.cmd")) {
  Write-Host "[download] actions runner"
  $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/actions/runner/releases/latest"
  $asset = $rel.assets | Where-Object { $_.name -match "win-x64-.*\.zip$" } | Select-Object -First 1
  if (-not $asset) { throw "Could not find win-x64 runner asset" }
  Invoke-WebRequest -Uri $asset.browser_download_url -OutFile runner.zip
  Expand-Archive -Path runner.zip -DestinationPath . -Force
  Remove-Item runner.zip -Force
}

Write-Host "[config] registering with labels self-hosted,Windows,ETHER"
& .\config.cmd --url $RepoUrl --token $Token --name "ether-windows-$env:COMPUTERNAME" --labels "self-hosted,Windows,ETHER" --work "_work" --unattended --replace

Write-Host "[service] install + start"
& .\svc.cmd install
& .\svc.cmd start

Write-Host ""
Write-Host "OK. Runner should show Idle at:"
Write-Host "  https://github.com/OxCryptobot/-ETHER/settings/actions/runners"
Write-Host "Then autonomy-host workflow can ensure daemon + E2E on this box."
