# @ETHER Status

**Batch 3 shipped** (2026-07-26): desktop launcher fixed, Matrix Flywheel panel, Rose stream option, tool-run payload-file, promote UI.

## Local recover
```powershell
cd C:\Users\Otcde\ETHER
$env:ETHER_GIT_RESET_OK = "1"
git fetch origin
git reset --hard origin/main
.\.venv\Scripts\python.exe -m pip install -e ".[dev]" -q
powershell -ExecutionPolicy Bypass -File .\scripts\install_desktop_shortcut.ps1
# or single window:
$env:ETHER_ROOT = "C:\Users\Otcde\ETHER"
.\.venv\Scripts\python.exe .\scripts\desktop_runtime.py
```

## Next (Batch 4)
1. Citrine index PASS patterns
2. Warm sandbox worker
3. Expand bench
4. Live stage ticker

## P3 reminder
Deferred until **2026-08-01**: LoRA, cloud burst, Firecracker, multi-agent, Obsidian.
