# Phase G — Sprint 1: surgical tool surface

## Status

| Item | Status |
|------|--------|
| `grep` / `glob` | ready (host apply) |
| `apply_patch` fail-closed | ready |
| `rollback` | ready |
| optional ruff in run_tests | ready (`ETHER_TOOL_RUFF=1`) |

## CRITICAL — if `core/tool_runtime.py` is the string `placeholder`

A bad push temporarily broke the file. Restore the last good version, then apply Phase G:

```powershell
cd C:\Users\Otcde\ETHER
git fetch origin
git reset --hard origin/main

# Restore last known-good tool_runtime
git show 65666a5:core/tool_runtime.py | Set-Content -Encoding utf8 core\tool_runtime.py

# Verify import
.\venv\Scripts\python.exe -c "from core.tool_runtime import ToolRuntime; print('OK', len(open('core/tool_runtime.py',encoding='utf-8').read()))"
```

## Then apply Phase G (after `scripts/apply_phaseg_full.py` is on main)

```powershell
.\venv\Scripts\python.exe scripts\apply_phaseg_full.py
.\venv\Scripts\python.exe -m pytest tests\test_tool_runtime.py -q
git add core/tool_runtime.py tests/test_tool_runtime.py
git commit -m "phaseG sprint1: grep/glob/apply_patch/rollback + ruff gate"
git push origin main
```

## Non-goals

- BoN / curriculum / flywheel online
- Full swarm
- Weight fine-tunes on host 4GB
