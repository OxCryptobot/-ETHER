# Install @ETHER launcher on the Desktop (double-click, single window)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Desktop = [Environment]::GetFolderPath("Desktop")
$BatSrc = Join-Path $Root "scripts\ETHER.bat"
$BatDst = Join-Path $Desktop "ETHER.bat"
$LnkPath = Join-Path $Desktop "ETHER Control Matrix.lnk"

Copy-Item -Force $BatSrc $BatDst

$Wsh = New-Object -ComObject WScript.Shell
$Sc = $Wsh.CreateShortcut($LnkPath)
$Sc.TargetPath = $BatDst
$Sc.WorkingDirectory = $Root
$Sc.WindowStyle = 1
$Sc.Description = "@ETHER single-window: auto-update + dashboard + flywheel"
$Sc.Save()

Write-Host "Installed:" -ForegroundColor Green
Write-Host "  $BatDst"
Write-Host "  $LnkPath"
Write-Host "Double-click 'ETHER Control Matrix' on your Desktop."
