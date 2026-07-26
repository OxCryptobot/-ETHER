# Local recovery (Windows)

## Symptoms
- `ModuleNotFoundError: No module named 'gems'` / `cli`
- `git pull` blocked by MERGE_HEAD
- `ether.exe` locked under Program Files
- PowerShell JSON breaks tool CLI

## One-shot recovery

```powershell
cd C:\Users\Otcde\ETHER
Stop-Process -Name python -Force -ErrorAction SilentlyContinue

git merge --abort 2>$null
git fetch origin
git reset --hard origin/main

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
if (Test-Path .\.venv) { Remove-Item -Recurse -Force .\.venv }
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e ".[dev]"

pytest tests/test_tools_catalog.py -q
python -m cli.main doctor
python -m cli.main dashboard
```

## Tool JSON on PowerShell
Use **single quotes** around the JSON object:

```powershell
python tools/persistent/secret_scan.py '{"text":"hello"}'
python tools/persistent/repo_map.py '{}'
```

Or key=value:

```powershell
python tools/persistent/secret_scan.py text=hello
```

## Restart flywheel / autonomy

```powershell
.\.venv\Scripts\Activate.ps1
python -m cli.main flywheel --push
# or
powershell -ExecutionPolicy Bypass -File .\scripts\autonomy.ps1
```
