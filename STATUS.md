# @ETHER Status

**2026-07-26 QA audit complete.** Core integrity hardened.

### What was broken / fixed
- `pytest` collection failed with `ModuleNotFoundError: No module named 'gems'` when package not editable-installed → fixed by `pythonpath = ["."]` in pyproject + `tests/conftest.py`.
- `tests/test_registry.py` asserted KeyError that `GemRegistry.get` never raised → test rewritten to match real behavior.
- PowerShell argv JSON to tools (`secret_scan` etc.) often produced `JSONDecodeError` → `_lib.py` coerce hardened for escaped quotes / mixed quoting.

### Run checks (after pull)
```powershell
git fetch origin; git reset --hard origin/main
.\.venv\Scripts\python.exe -m pip install -e ".[dev]" -q
.\.venv\Scripts\python.exe .\scripts\health_check.py --skip-sandbox
.\.venv\Scripts\python.exe -m pytest -q
```

Linux:
```bash
git fetch origin && git reset --hard origin/main
source .venv/bin/activate && pip install -e ".[dev]" -q
python scripts/health_check.py --skip-sandbox
python -m pytest -q
```

### Health API
- `GET /api/health-check?skip_sandbox=true`
- `POST /api/health-check` `{"skip_sandbox": true}`

Writes `memory/health/latest.json` + history.jsonl.
