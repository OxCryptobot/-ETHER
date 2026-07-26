# @ETHER Desktop (single window)

## Install shortcut (once)

```powershell
cd C:\Users\Otcde\ETHER
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
git fetch origin
git reset --hard origin/main
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
powershell -ExecutionPolicy Bypass -File .\scripts\install_desktop_shortcut.ps1
```

This creates on your **Desktop**:
- `ETHER.bat`
- `ETHER Control Matrix.lnk`

## Daily use

**Double-click** `ETHER Control Matrix` on the Desktop.

One window does everything:
1. Auto `git fetch` + `reset --hard origin/main` (when `ETHER_GIT_RESET_OK=1`)
2. Quiet `pip install -e .[dev]`
3. Starts **dashboard** at http://127.0.0.1:8787
4. Opens browser
5. Runs **flywheel autonomy** in the same process (interval from `.env`, default 900s)
6. Prints live status in that console

**Ctrl+C** in that window stops everything.

## Env (optional in `.env`)

```
ETHER_GIT_RESET_OK=1
ETHER_PULL_SOFT=1
ETHER_FLYWHEEL_PUSH=1
ETHER_FLYWHEEL_INTERVAL=900
ETHER_PRIMARY_MODEL=qwen2.5-coder:3b
ETHER_OPEN_BROWSER=1
ETHER_DASH_PORT=8787
```
