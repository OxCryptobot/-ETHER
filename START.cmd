@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ========================================
echo  ETHER — one window (host + dashboard)
echo  UI: http://127.0.0.1:8787/
echo ========================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_ether_host.ps1"
set EXITCODE=%ERRORLEVEL%
echo.
if not "%EXITCODE%"=="0" (
  echo Exited with code %EXITCODE%
  pause
)
exit /b %EXITCODE%
