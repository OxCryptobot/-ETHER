@echo off
REM @ETHER one-click desktop launcher (single window)
cd /d "%~dp0.."

set ETHER_GIT_RESET_OK=1
set ETHER_PULL_SOFT=1
set ETHER_FLYWHEEL_PUSH=1
set ETHER_OPEN_BROWSER=1
set PYTHONIOENCODING=utf-8

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "scripts\desktop_runtime.py"
) else (
  echo Creating venv...
  python -m venv .venv
  ".venv\Scripts\python.exe" -m pip install -U pip
  ".venv\Scripts\python.exe" -m pip install -e ".[dev]"
  ".venv\Scripts\python.exe" "scripts\desktop_runtime.py"
)

echo.
echo @ETHER stopped. Press any key to close.
pause >nul
