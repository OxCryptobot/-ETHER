# Install @ETHER launcher on Desktop — points at REPO scripts, not a broken Desktop copy
$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RepoBat = Join-Path $Root "scripts\ETHER.bat"
$Desktop = [Environment]::GetFolderPath("Desktop")
$DesktopBat = Join-Path $Desktop "ETHER.bat"
$LnkPath = Join-Path $Desktop "ETHER Control Matrix.lnk"

if (-not (Test-Path $RepoBat)) {
  Write-Error "Missing $RepoBat — run this from the @ETHER repo."
}

# Desktop BAT is a thin wrapper that sets ETHER_ROOT then calls repo BAT
$wrapper = @"
@echo off
set ETHER_ROOT=$Root
call "$RepoBat"
"@
Set-Content -Path $DesktopBat -Value $wrapper -Encoding ASCII

$Wsh = New-Object -ComObject WScript.Shell
$Sc = $Wsh.CreateShortcut($LnkPath)
$Sc.TargetPath = $DesktopBat
$Sc.WorkingDirectory = $Root
$Sc.WindowStyle = 1
$Sc.Description = "@ETHER single-window: auto-update + dashboard + flywheel"
$Sc.Save()

Write-Host ""
Write-Host "Installed successfully:" -ForegroundColor Green
Write-Host "  Shortcut : $LnkPath"
Write-Host "  Wrapper  : $DesktopBat"
Write-Host "  Repo BAT : $RepoBat"
Write-Host "  Root     : $Root"
Write-Host ""
Write-Host "Double-click 'ETHER Control Matrix' on your Desktop."
Write-Host "One window = git update + dashboard + flywheel."
