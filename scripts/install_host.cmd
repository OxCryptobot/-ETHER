@echo off
rem Run ONCE on the 1650 (no admin needed). Idempotent: safe to re-run.
rem Removes every legacy ETHER starter, registers the one ETHER-Host task,
rem starts it and prints status. Add --boot from an admin prompt to run before logon.
call "%~dp0host.cmd" install %*
exit /b %ERRORLEVEL%
