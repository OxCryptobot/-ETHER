# Host sprints

Sprint files are executed by `scripts/host_runner.ps1`.

## Format

```powershell
# STEP: short_name
command one
# STEP: next
command two
```

Env vars persist across steps (same PowerShell process).

## Run

```powershell
cd C:\Users\Otcde\ETHER
.\scripts\host_runner.ps1 -Sprint phaseg_wire -PushReport
```

`-PushReport` commits `artifacts/host_report_latest.md` so the next chat turn can read it from GitHub without pasting.
