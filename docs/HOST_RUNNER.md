# Host runner — close the chat ↔ machine loop

## Problem

Grok posts PowerShell; you paste results; lag kills sprint velocity.

## Solution

1. Grok writes a sprint file under `scripts/sprints/`.
2. You run **one** command:
   ```powershell
   .\scripts\host_runner.ps1 -Sprint <name> -PushReport
   ```
3. Runner executes each `# STEP`, captures stdout/stderr/exit/timing.
4. Writes `artifacts/host_report_latest.md` + `.json`.
5. With `-PushReport`, commits and pushes so Grok fetches the report on the next turn.

## Commands

| Sprint | Purpose |
|--------|---------|
| `phaseg_wire` | Restore tool_runtime, wire Phase G tools, pytest, scripted hard |
| `phaseg_live_f` | Phase F live re-measure (GPU, long) |

## New sprint (Grok side)

Add `scripts/sprints/foo.ps1` with `# STEP:` blocks, then ask you to run:

```powershell
.\scripts\host_runner.ps1 -Sprint foo -PushReport
```

## Fetch report (Grok)

```
GitHub get_file_contents: artifacts/host_report_latest.md
```
