# @ETHER Status

**Intelligence layer live** (curriculum + experience vault + bench guardian).

```powershell
cd C:\Users\Otcde\ETHER
$env:ETHER_GIT_RESET_OK = "1"
git fetch origin
git reset --hard origin/main
.\.venv\Scripts\python.exe -m pip install -e ".[dev]" -q
.\.venv\Scripts\python.exe .\scripts\bench.py
powershell -ExecutionPolicy Bypass -File .\scripts\start_daemon.ps1 -Foreground
```

See **INTELLIGENCE.md** and **OPS.md**.
