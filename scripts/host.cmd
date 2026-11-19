@echo off
rem ETHER host control. One command for people and bots:
rem   scripts\host.cmd setup ^| install ^| start ^| stop ^| restart ^| status ^| once ^| uninstall
setlocal
set "ROOT=%~dp0.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"
set "ETHER_ROOT=%ROOT%"
set "PYTHONPATH=%ROOT%"
set "PYTHONIOENCODING=utf-8"
set "PY=%ROOT%\.venv\Scripts\python.exe"
if /i "%~1"=="setup" goto setup
if not exist "%PY%" (
  echo {"ok": false, "error": "no_venv", "fix": "scripts\host.cmd setup"}
  exit /b 1
)
"%PY%" "%ROOT%\scripts\host_ctl.py" %*
exit /b %ERRORLEVEL%

:setup
rem venv + editable install. No git reset, no process killing.
cd /d "%ROOT%"
if not exist "%PY%" (
  where py >nul 2>nul && (py -3 -m venv .venv) || (python -m venv .venv)
)
if not exist "%PY%" (
  echo {"ok": false, "error": "python_missing", "fix": "install Python 3.11+ from python.org, then re-run"}
  exit /b 1
)
"%PY%" -m pip install -q -U pip
"%PY%" -m pip install -q -e .
exit /b %ERRORLEVEL%
