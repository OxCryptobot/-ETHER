# @ETHER Status

**Updated:** 2026-08-14T20:41Z — Permanent host fix landed. Soft launch still BLOCKED until measured.

---

## Permanent solutions (this sprint)

### Host never idle again
- `scripts/host_agent.py` now calls `foreman.tick()` on:
  - startup bootstrap
  - every empty-pending cycle
  - after jobs when depth < 5
- System no longer depends on chat/Grok to keep the queue moving.

### Queue auto-fills forever
- `scripts/foreman.py` after curriculum exhaustion enters **steady mode**:
  - rotates `ss_direct_hard`, `ss_pipeline_ledger`, `ss_train_gates`, `ss_tool_runtime`, `ss_archive_failed`
  - unique timestamp ids each tick (no infinity z_gate)
  - BATCH_SIZE=10 kept

### Failed jobs cleaned
- Steady template `ss_archive_failed` moves noise out of `failed/` into `failed_archived/`
- Playbook recovery still converts recovered FAILs to done/

### Pipeline stability (earlier)
- `core/pipeline.py` restored + `tool_runtime_failed_terminal` (closes 984s hang)

## Phase 1 board

| Package | Status |
|---------|--------|
| 1A Tool-first | COMPLETE |
| 1B AgentState | COMPLETE |
| 1C AST transactional | COMPLETE |
| 1D Measured lift | IN PROGRESS — host must pull + re-measure |

## What you must do once (host)

If host is still running old code, restart it so it pulls main:

```powershell
cd C:\Users\Otcde\ETHER
git fetch origin
git reset --hard origin/main
.\scripts\start_ether_host.ps1
```

After restart: host boots → foreman.tick() → pending fills → work continues with or without Grok.

Training wheels ON. Soft launch blocked until measured lift is honest.
