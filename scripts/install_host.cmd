@echo off
rem Run ONCE on the 1650 (no admin needed). Idempotent: safe to re-run.
rem Creates the venv if missing, removes every legacy ETHER starter,
rem registers the one ETHER-Host task, starts it and prints status.
rem Add --boot from an admin prompt to also run before anyone logs on.
if not exist "%~dp0..\.venv\Scripts\python.exe" call "%~dp0host.cmd" setup || exit /b 1
call "%~dp0host.cmd" install %*
exit /b %ERRORLEVEL%
