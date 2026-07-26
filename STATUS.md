# @ETHER Status

**Through 81 on main:** ledger, compare runner, scratch tier, Matrix ledger fields.

```powershell
cd C:\Users\Otcde\ETHER
$env:ETHER_GIT_RESET_OK = "1"
git fetch origin
git reset --hard origin/main
.\.venv\Scripts\python.exe -m pip install -e ".[dev]" -q
.\.venv\Scripts\python.exe .\scripts\expand_holdout.py
.\.venv\Scripts\python.exe .\scripts\wire_check.py
.\.venv\Scripts\python.exe -m pytest -q
```
