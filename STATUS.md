# @ETHER Status

**P0–P2 critical upgrades shipped** (2026-07-26).

## Recover local
```powershell
cd C:\Users\Otcde\ETHER
$env:ETHER_GIT_RESET_OK = "1"
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1
python -m cli.main doctor
python -m cli.main dashboard
python scripts\bench.py
```

## P3 reminder
Deferred until **2026-08-01**: LoRA, cloud burst depth, Firecracker, multi-agent, Obsidian.
