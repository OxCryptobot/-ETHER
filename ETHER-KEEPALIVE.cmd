@echo off
cd /d C:\Users\Otcde\ETHER
echo ETHER keepalive starting...
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe scripts\ether_keepalive.py
) else (
  python scripts\ether_keepalive.py
)
echo keepalive exited %ERRORLEVEL%
pause
