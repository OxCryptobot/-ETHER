@echo off
setlocal EnableExtensions
REM @ETHER launcher — always run from repo, never depend on Desktop location

REM If ETHER_ROOT is set (Desktop wrapper), use it; else scripts\.. is repo root
if defined ETHER_ROOT (
  cd /d "%ETHER_ROOT%"
) else (
  cd /d "%~dp0.."
)

if not exist "scripts\desktop_runtime.py" (
  echo [ERROR] Cannot find @ETHER repo.
  echo Expected scripts\desktop_runtime.py under:
  echo   %CD%
  echo.
  echo Fix: re-run scripts\install_desktop_shortcut.ps1 from the repo.
  echo.
  pause
  exit /b 1
)

set ETHER_GIT_RESET_OK=1
set ETHER_PULL_SOFT=1
set ETHER_FLYWHEEL_PUSH=1
set ETHER_OPEN_BROWSER=1
set PYTHONIOENCODING=utf-8

echo.
echo  @ETHER desktop runtime
echo  Repo: %CD%
echo.

if not exist ".venv\Scripts\python.exe" (
  echo Creating venv...
  where python >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] python not found on PATH
    pause
    exit /b 1
  )
  python -m venv .venv
  ".venv\Scripts\python.exe" -m pip install -U pip
  ".venv\Scripts\python.exe" -m pip install -e ".[dev]"
)

".venv\Scripts\python.exe" "scripts\desktop_runtime.py"
set EXITCODE=%ERRORLEVEL%

echo.
if not "%EXITCODE%"=="0" (
  echo @ETHER exited with code %EXITCODE%
) else (
  echo @ETHER stopped cleanly.
)
echo Press any key to close.
pause >nul
exit /b %EXITCODE%
