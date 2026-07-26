# @ETHER Status

**Batch 66–70 on main:** process rewards, burst-on-retry, daemon quiz, TASKS refreshed.

```powershell
cd C:\Users\Otcde\ETHER
$env:ETHER_GIT_RESET_OK = "1"
git fetch origin
git reset --hard origin/main
.\.venv\Scripts\python.exe -m pip install -e ".[dev]" -q
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe .\scripts\bootstrap_intel.py
```

Burst-on-fail is default when `ETHER_BURST=1` and key is set; retry elevates model.
