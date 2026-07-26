# @ETHER Status

**76–81 closed on main.**

```powershell
cd C:\Users\Otcde\ETHER
$env:ETHER_GIT_RESET_OK = "1"
git fetch origin
git reset --hard origin/main
.\.venv\Scripts\python.exe -m pip install -e ".[dev]" -q
.\.venv\Scripts\python.exe .\scripts\expand_holdout.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe .\scripts\compare_run.py --limit 3
```

Ledger: `memory/ledger/latest.json` · Compare: `memory/bench/compare_YYYYMMDD.md`
