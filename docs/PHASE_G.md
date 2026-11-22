# Phase G — Tool surface expansion

## Status

- **job_phaseg_verify_003 PASS** (2026-08-07T18:00:09Z)
  - restore + wire + import + pytest + scripted hard 5/5 on host
- Tools added: `grep`, `glob`, `apply_patch`, `rollback` via `core/tool_runtime_ext.py`
- Host agent job queue operational (direct argv path; PowerShell path-rewrite abandoned)
- Status: the Grok Control Matrix (read-only) reads `artifacts/unison.json`, `supervisor.json` and `learning_summary.json` from origin; locally `scripts/ether_app.py` serves a read-only watch page on http://127.0.0.1:7843/. The old :8787 dashboard is retired (writes refused, batch 9).

## Operating rule

Failed host reports are immediate fix + requeue. Direct `argv` jobs preferred over `host_runner` sprints for Python work.

## Remaining

- Land wired `core/tool_runtime.py` on origin (job `land_runtime_001`)
- Phase G FINDINGS close-out after origin is non-placeholder
