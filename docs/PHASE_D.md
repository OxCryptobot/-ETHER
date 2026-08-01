# Phase D — Repo-grounded eval + e2e tool path

## Status

| Slice | Content | Status |
|-------|---------|--------|
| 1 | Pipeline e2e under `ETHER_TOOL_RUNTIME=1` | **CLOSED** (ledger PASS: tool→workspace_verify→repo_ok) |
| 2 | Task pack (`fixtures/phase_d_tasks.json`) | **ACTIVE** |
| 3 | Bare vs direct vs pipeline batch | **ACTIVE** |
| 4 | FINDINGS / STATUS numbers | pending batch results |

## Batch (preferred)

```powershell
git fetch origin; git reset --hard origin/main

# Fast offline: scripted direct hard (no GPU)
python -m scripts.batch_phase_d --arm direct --mode scripted --tier hard

# Live comparison (sequential GPU) — direct + pipeline + bare
python -m scripts.batch_phase_d --arm all --mode live --tier hard --timeout 400

# Pipeline only
python -m scripts.batch_phase_d --arm pipeline --mode live --tier hard --timeout 400
```

Scoreboard: `artifacts/scoreboard_phase_d.json`

## Arms

| Arm | Meaning |
|-----|---------|
| **direct** | `ToolRuntime` only (Phase C) |
| **pipeline** | `Pipeline.run` + tool runtime ON + workspace re-verify |
| **bare** | `Pipeline.run` tool runtime OFF (generate-only control) |

## Slice 1 closed criteria (ledger)

```
tool_runtime ok score=1.0
sandbox workspace_verify exit=0 score=1.0
repo_ok=True
```

## Non-goals

- Curriculum / bandit / flywheel re-enable
- Shell tools
- Best-of-N revival
