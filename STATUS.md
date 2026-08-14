# @ETHER Status

**Updated:** 2026-08-14T19:20Z — Scoreboards landing. Pipeline live hang diagnosed and hardened. Soft launch still gated.

---

## Doctrine (locked)

- GEMS core — streamline only, never remove
- Training wheels ON until measured lift on expanded repo-oracle
- One hypothesis per job; Labradorite mandatory on non-infra FAIL
- Tool-first is the required direction
- LoRA dual-flag gated; dry-run default only
- **Every FAIL → critique + lesson + smallest experiment**
- Soft launch blocked until Phase 1 gate is fully green

---

## Phase 1 board

| Package | Status |
|---------|--------|
| 1A Tool-first default | **COMPLETE** |
| 1B AgentState durable | **COMPLETE** |
| 1C AST transactional edits | **COMPLETE** |
| 1D Expand eval + measured lift | **IN PROGRESS** — numbers now honest |

### Measured numbers (origin)

| Arm | Mode | Hard pack | Result |
|-----|------|-----------|--------|
| **direct** | scripted | 5 fixtures | **5/5** (p1_07, p1_11, p1_19) |
| pipeline | live | 1 fixture (lru) | 0/1 max_steps → was hanging 16min (now hardened) |

**Signal:** Pure ToolRuntime (direct) is the best-in-class path on this hardware. Pipeline-wrapped live was burning wall-clock after tool_runtime failure.

### Hardening this turn

- `batch_phase_d` sentinel scoreboard on entry (already landed)
- Pipeline: tool_runtime non-ok is now **terminal** under tool-first — no multi-minute generate fallback
- Labradorite critique written for p1_18

### Remaining for full Phase 1 green / soft launch

1. Confirm hardened Pipeline no longer hangs (p1_21 / p1_22)
2. Expand hard fixtures 5 → ≥10
3. train_gates final green (p1_24)
4. Honest STATUS with all numbers on origin

Host is live. Pending continues. Training wheels ON.
