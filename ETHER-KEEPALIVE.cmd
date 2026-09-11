@echo off
REM Double-click on the 1650. Not an operator PowerShell ritual.
cd /d C:\Users\Otcde\ETHER
if exist .venv\Scripts\python.exe (
  start "" /MIN .venv\Scripts\python.exe scripts\ether_keepalive.py
) else (
  start "" /MIN python scripts\ether_keepalive.py
)
