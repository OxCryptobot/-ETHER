# @ETHER Status

**Updated:** 2026-08-08 20:01 — Package 1A tool-first default landed. Host idle after tw_e08 PASS.

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
| Tests | **763+** |
| Verification | held-out grading, mutation score 0.966 |
| Leak channels closed | **7** |
| `main` | green on fresh clone for core tests |
| **Does ETHER beat a bare model on holdout generate?** | **No** (ablation stands) |
| **Does tool-runtime beat bare on hard repo-oracle pack?** | **Yes** (Phase D 5/5) |
| AgentState | skeleton landed + wired into EvolutionController |
| LoRA path | data prep + dry-run live; real train dual-flag gated |
| Evolution loop | introspection mandatory; __main__ hardened; tw_e08 PASS |
| **Tool-first default (1A)** | **LANDED** — defaults ON under training wheels |

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
| 1B AgentState durable | WIRED into EvolutionController | create/save/load round-trip; shared by gems |
| 1C AST transactional edits | QUEUED | Python-first; snapshot + rollback on test fail |
| 1D Expand eval + close current FAILs | IN PROGRESS | evolution re-verify PASS (tw_e08); expand suite next |

**Gate to Phase 2:** Tool-first live, AgentState durable across restart, ≥10 hard tasks measured with pipeline lift, evolution FAILs closed.

### Phases 2–7
See implementation blueprint. Do not start until Phase 1 gate is green.

---

## What genuinely works

- Holdout, prompt_guard, assert_audit, ablation culture
- Fail-closed sandbox
- Tool runtime + Clear Quartz on repo-oracle tasks
- Labradorite structured root_cause + smallest_experiment
- Offline preference pairs + train_gates
- GEMS topology (non-negotiable)
- AgentState durable shared state
- **Tool-first default under training wheels (Package 1A)**

## Hazards

- Lifting training wheels without measured lift destroys the preference signal
- Generation-first default continues to lose to bare model
- Real LoRA before clean data + dual flags is forbidden
- A red `main` kills the other machine — `pytest && git push`

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

## Next action only

1. Host drains tw_e09_tool_first_default (expect PASS)
2. Expand repo-oracle suite to ≥10 hard tasks and measure pipeline lift
3. Land 1C AST transactional edits only after measurement
4. Only after measured lift: discuss wheels
