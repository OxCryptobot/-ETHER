# @ETHER Status

**76–81 on main:** latency ledger, compare runner, scratch curriculum tier, strategy context helper.

```powershell
cd C:\Users\Otcde\ETHER
$env:ETHER_GIT_RESET_OK = "1"
git fetch origin
git reset --hard origin/main
.\.venv\Scripts\python.exe -m pip install -e ".[dev]" -q
.\.venv\Scripts\python.exe .\scripts\expand_holdout.py
.\.venv\Scripts\python.exe -c "from core.ledger import compute_ledger; import json; print(json.dumps(compute_ledger(), indent=2))"
.\.venv\Scripts\python.exe -m pytest -q
```
