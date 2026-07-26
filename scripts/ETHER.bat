@echo off
setlocal EnableExtensions
REM @ETHER launcher — MUST be given absolute ETHER_ROOT by desktop wrapper

if not defined ETHER_ROOT (
  REM Fallback only when launched from repo\scripts\
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

if not exist "%CD%\scripts\desktop_runtime.py" (
  echo [ERROR] desktop_runtime.py not found.
  echo ETHER_ROOT was: %ETHER_ROOT%
  echo Current dir is: %CD%
  echo.
  echo Your Desktop is likely under OneDrive. Re-install the shortcut FROM the repo:
  echo   cd C:\Users\Otcde\ETHER
  echo   powershell -ExecutionPolicy Bypass -File .\scripts\install_desktop_shortcut.ps1
  echo.
  pause
  exit /b 1
)

set ETHER_GIT_RESET_OK=1
set ETHER_PULL_SOFT=1
set ETHER_FLYWHEEL_PUSH=1
set ETHER_OPEN_BROWSER=1
set PYTHONIOENCODING=utf-8

set "VENV_PY=%CD%\.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
  echo Creating venv in %CD%\.venv ...
  where python >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] python not on PATH
    pause
    exit /b 1
  )
  python -m venv .venv
  "%CD%\.venv\Scripts\python.exe" -m pip install -U pip
  "%CD%\.venv\Scripts\python.exe" -m pip install -e ".[dev]"
  set "VENV_PY=%CD%\.venv\Scripts\python.exe"
)

echo Using: %VENV_PY%
echo.
"%VENV_PY%" "%CD%\scripts\desktop_runtime.py"
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
