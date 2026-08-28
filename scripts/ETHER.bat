@echo off
setlocal EnableExtensions
REM @ETHER one-click launcher — starts ether_host (dashboard + job drain)

if not defined ETHER_ROOT (
  pushd "%~dp0.." >nul
  set "ETHER_ROOT=%CD%"
  popd >nul
)

cd /d "%ETHER_ROOT%" 2>nul
if errorlevel 1 (
  echo [ERROR] Cannot cd to ETHER_ROOT=%ETHER_ROOT%
  pause
  exit /b 1
)

echo Repo root: %CD%

if not exist "%CD%\scripts\start_ether_host.ps1" (
  echo [ERROR] start_ether_host.ps1 not found.
  echo ETHER_ROOT was: %ETHER_ROOT%
  echo Current dir is: %CD%
  echo Re-install the shortcut FROM the repo:
  echo   cd C:\Users\Otcde\ETHER
  echo   powershell -ExecutionPolicy Bypass -File .\scripts\install_desktop_shortcut.ps1
  pause
  exit /b 1
)

set ETHER_GIT_RESET_OK=1
set ETHER_PULL_SOFT=1
set ETHER_OPEN_BROWSER=1
set PYTHONIOENCODING=utf-8

powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\start_ether_host.ps1"
set EXITCODE=%ERRORLEVEL%

echo.
if not "%EXITCODE%"=="0" (
  echo @ETHER exited with code %EXITCODE%
) else (
  echo @ETHER stopped.
)
echo Press any key to close.
pause >nul
exit /b %EXITCODE%
