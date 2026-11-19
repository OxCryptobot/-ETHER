@echo off
rem ETHER host control. One command for people and bots:
rem   scripts\host.cmd install ^| start ^| stop ^| restart ^| status ^| once ^| uninstall
setlocal
set "ROOT=%~dp0.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"
set "ETHER_ROOT=%ROOT%"
set "PYTHONPATH=%ROOT%"
set "PYTHONIOENCODING=utf-8"
set "PY=%ROOT%\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo {"ok": false, "error": "no_venv", "fix": "cd /d %ROOT% ^&^& py -3.12 -m venv .venv ^&^& .venv\Scripts\python -m pip install -e ."}
  exit /b 1
)
"%PY%" "%ROOT%\scripts\host_ctl.py" %*
exit /b %ERRORLEVEL%
