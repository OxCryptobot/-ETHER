# @ETHER Status

**Updated:** 2026-08-14 — Package 1C AST transactional edits landed (core/ast_transaction.py + tests). Host still offline since 2026-08-08; recovery already issued once. Training wheels stay ON. Phase 1 gate unchanged.

Read `docs/FINDINGS.md` and `docs/GEM_EVOLUTION.md` before changing anything.

---

## Non-negotiable doctrine (2026-08-08)

- **GEMS are core.** Streamline only. Never remove or dilute the gem topology.
- **Training wheels stay ON** until measured lift on expanded repo-oracle suite.
- One hypothesis per job/cycle. Labradorite structured critique mandatory on non-infra FAIL.
- LoRA / weight updates gated by dual flags + holdout. Dry-run is the only default.
- **Tool-first is the required direction.** Generation-first is no longer the default target.

---

## Where the project actually is

| | |
|---|---|
| Tests | **763+** (plus new 1C suite) |
| Verification | held-out grading, mutation score 0.966 |
| Leak channels closed | **7** |
| `main` | green on fresh clone for core tests |
| **Does ETHER beat a bare model on holdout generate?** | **No** (ablation stands) |
| **Does tool-runtime beat bare on hard repo-oracle pack?** | **Yes** (Phase D 5/5) |
| AgentState | skeleton landed + wired into EvolutionController |
| LoRA path | data prep + dry-run live; real train dual-flag gated |
| Evolution loop | introspection mandatory; __main__ hardened; tw_e08 PASS |
| **Tool-first default (1A)** | **LANDED** — defaults ON under training wheels |
| **Dashboard SUPER APP** | **LANDED** — unified Host + Control Matrix at /agent |
| **Foreman** | **REVAMPED** — sequential batch fill (BATCH_SIZE=3), recovered conversion, Phase 1 remaining items |
| **AST transactional edits (1C)** | **LANDED** — EditTransaction + verify_and_commit + full test suite |

### Holdout generate (unchanged)

| model | bare | bare+sys | ether |
|---|---|---|---|
| `qwen2.5:3b` | 0.317 | 0.333 | 0.292 |

`ether − bare+sys = −0.042`. Agent loop remains net negative on pure generate. **Any pre-audit conf=1.000 is void.**

### Phase D — hard repo-oracle (host `qwen3.5:4b`)

| arm | hard 5 |
|-----|--------|
| **direct** (ToolRuntime) | **5/5** |
| **pipeline** | **5/5** |
| **bare** | **0/5** |

This is the signal we are amplifying.

---

## Active rollout (from engineering audit + blueprint)

### Phase 1 — Critical Fixes (IN PROGRESS)

| Package | Status | Success criteria |
|---------|--------|------------------|
| 1A Tool-first default | **LANDED** | tool_runtime only default under wheels; Phase D still 5/5 |
| 1B AgentState durable | **WIRED** into EvolutionController | create/save/load round-trip; shared by gems |
| 1C AST transactional edits | **LANDED** | Python-first; snapshot + rollback on test fail |
| 1D Expand eval + close current FAILs | IN PROGRESS | evolution re-verify PASS (tw_e08); expand suite next (p1_03/04/05 now in curriculum) |

**Gate to Phase 2:** Tool-first live, AgentState durable across restart, ≥10 hard tasks measured with pipeline lift, evolution FAILs closed.

### Phases 2–7
See implementation blueprint. Do not start until Phase 1 gate is green.

---

## Dashboard (SUPER APP)

- URL: `http://127.0.0.1:8787/agent`
- Unified view: Phase 1 board (live from STATUS.md) + Host Agent queue/log/status + Control Matrix live coding feed + GEMS flow + code preview
- Poll 1.5 s; paths under `artifacts/` only (collector_host_agent fixed)
- `/api/host-agent` + `/api/snapshot` both consumed
- Recovery banner surfaces when host heartbeat is stale

## What genuinely works

- Holdout, prompt_guard, assert_audit, ablation culture
- Fail-closed sandbox
- Tool runtime + Clear Quartz on repo-oracle tasks
- Labradorite structured root_cause + smallest_experiment
- Offline preference pairs + train_gates
- GEMS topology (non-negotiable)
- AgentState durable shared state
- **Tool-first default under training wheels (Package 1A)**
- **SUPER APP dashboard (Host + Control Matrix consolidated)**
- **Foreman sequential batch + recovered FAIL conversion**
- **AST transactional edits (Package 1C) — snapshot + rollback**

## Hazards

- Lifting training wheels without measured lift destroys the preference signal
- Generation-first default continues to lose to bare model
- Real LoRA before clean data + dual flags is forbidden
- A red `main` kills the other machine — `pytest && git push`
- Host offline > few minutes blocks the entire curriculum

## Running it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env

pytest -q
python -m cli.main doctor
python -m core.lora_train          # dry-run only under wheels
python -m core.evolution_loop      # introspection cycle (now clean exit)
```

Host (one window):
```powershell
cd C:\Users\Otcde\ETHER
git fetch origin
git reset --hard origin/main
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\start_ether_host.ps1
```

## Next action only

1. Host recovery (already issued once) — poll artifacts/host_agent_status.json
2. Labradorite structured critique of p1_04 FAIL, then single smallest measurement follow-up
3. Wire EditTransaction into tool_runtime write path (post-host recovery)
4. Expand repo-oracle to ≥10 hard tasks and re-measure pipeline lift
5. Only after measured lift: discuss wheels
