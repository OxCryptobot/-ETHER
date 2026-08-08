---
name: host-agent-live
description: Drive ETHER host agent job queue on the Windows GPU host via GitHub pending jobs, reports, and dashboard. Use when user says host agent live, host agent, job queue, pending jobs, sprint delivery, batch host, ether_host, foreman, train gates, or asks to run work on their machine without pasting logs. Also use for dashboard revamps, GEMS engagement on FAIL, RLHF observability, and E2E workflow diagnosis.
---

# Host Agent Live (v2 — E2E + GEMS)

Close the chat ↔ Windows host loop for repo `OxCryptobot/-ETHER` without manual PowerShell paste every step.  
**Training wheels mode is the default until explicitly lifted.** One hypothesis per job. `continue_on_fail` only when measuring. No budget bumps until root cause is proven.

## Architecture (hard facts)

| Actor | Can do |
|-------|--------|
| Grok (this chat) | Push code and job JSON to GitHub; read reports from GitHub; write lessons + skill updates |
| ether_host on Windows | git pull, run jobs, push reports, advance curriculum, apply playbooks, serve dashboard |
| Grok cannot | Execute processes on the user PC |

Without `scripts/ether_host.py` running on the host, jobs sit in pending forever.

## Git policy (never stuck)

The agent is a **consumer**, not a feature branch. Origin always wins.

| When | Action |
|------|--------|
| Startup | `git fetch` + `git reset --hard origin/main` |
| Each poll | ff-only merge; if diverged → hard reset to origin |
| Push report fails | one rebase retry; if still fail → hard reset (do not stay diverged) |
| `ff-only failed` spam | treat as git divergence, **not** a test failure |

`start_ether_host.ps1` also resets to origin before launch. After a one-time restart onto this version, **do not ask the user to manually reset** again.

Do not confuse `push rc=1` or `ff-only failed` with pytest/job failure. Check `JOB END … ok=True/False` only.

## One window (user only — last manual step)

```powershell
cd C:\Users\Otcde\ETHER
git fetch origin
git reset --hard origin/main
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\start_ether_host.ps1
```

Single console: dashboard thread + host_agent loop + foreman.tick().

**Launcher behavior (critical):**
- Exit code 0 (Ctrl+C) → stop permanently
- Exit code 42 (source updated) → restart in 1s
- ANY other exit / crash → restart with backoff (never stays dead)

You start it once. After that the launcher keeps it alive. Do not ask the user to restart again under normal conditions.

- URL — `http://127.0.0.1:8787/agent`
- API — `GET /api/host-agent` (queue, log, foreman cursor, apprentice lessons, RLHF, gems)

## Hard rules for Grok (this skill)

- NEVER ask the user to watch the dashboard.
- NEVER ask the user to tell you the job result.
- ALWAYS read results yourself from GitHub:
  - `artifacts/host_agent_last_job.json`
  - `artifacts/host_agent_status.json` (liveness heartbeat, pushed every ~60s while idle)
  - recent `host agent report:` / `host agent liveness` commits
  - `artifacts/preference_summary.json`, `artifacts/preferences_tail.jsonl`, `artifacts/strategy_stats.json`
  - any `artifacts/scoreboard*.json` and `artifacts/trace_*.json`
- If host appears dead (stale heartbeat + pending job not consumed for >2 min), give the one recovery block above ONCE, then resume reading state yourself.
- Status lives under `artifacts/` (tracked). Never rely on `memory/` for remote observability — it is gitignored.
- **Dashboard path rule**: collector_host_agent and agent.html MUST read the same paths host_agent writes (`artifacts/host_agent_status.json`, `artifacts/host_agent_log.txt`, `artifacts/host_agent_last_job.json`). Mismatch is a P0 bug.

## Primary loop (ether_host)

1. Push implementation to `main` via GitHub tools.
2. Enqueue work as `artifacts/jobs/pending/<id>.json`.
3. Host drains FIFO (sorted by filename), back-to-back.
4. After every job: `agent.git_sync()` then `foreman.tick()`.
5. Foreman on idle enqueues next curriculum item; on FAIL applies matching playbook (guarded).
6. Agent pushes `artifacts/host_agent_last_job.json` and moves job to `done/` or `failed/`.
7. On FAIL — diagnose with GEMS (see below), fix root cause, requeue a new job id, do not wait for the user to ask.
8. On PASS — continue next pending or let foreman advance.

## Failure diagnosis protocol (no more blind retries)

We cannot ship failures. Every non-infra FAIL must produce an exact cause before the next experiment.

### Taxonomy (use these labels only)

| Code | Meaning | Typical signal |
|------|---------|----------------|
| `tool_order` | Wrong tool sequence / missing read-first | max_steps with zero useful tool results |
| `repair_quality` | Patch applied but still fails tests | score < 0.99 after edit tools |
| `parse_fail` | Action / JSON parse error | parse exceptions in trace |
| `budget_exhaust` | Hit max_steps cleanly | n_steps == max_steps, no early abort |
| `trace_missing` | Scoreboard or trace never landed on origin | git_push_report ran but file absent |
| `preference_pollution` | Infra rows entered preference pairs | boosts contaminated |
| `infra` | Docker / Ollama / timeout_infra / connection | never enter FAIL vault or preference rejected |
| `unknown` | Must not stay unknown >1 job | force Labradorite |

### Mandatory GEMS engagement on FAIL

Gems exist for this exact purpose. The infinity topology is not optional documentation.

```
Selenite (plan) → Rose Quartz (route) → Clear Quartz (sandbox exec)
        ↑                                           │
        │                                           ▼
   Amethyst (log + RL signal)  ←  Labradorite (critique ALWAYS)
```

**On every code FAIL (training wheels):**

1. Enqueue a **Labradorite critique job** (id pattern `lab_crit_<fail_job_id>`).  
   Input: the failed job envelope + available scoreboard/trace.  
   Output required: `artifacts/critique_<id>.json` containing:
   - `root_cause` (one of the taxonomy codes above)
   - `evidence` (short quotes from log/trace)
   - `smallest_experiment` (exact next job JSON or argv)
   - `confidence` (0–1)
2. Amethyst records the outcome for bandit / strategy_stats / preference signal.
3. Clear Quartz is the only executor for the resulting experiment (sandbox verified).
4. Rose Quartz decides model/strategy only after critique is present.
5. Never enqueue a second hypothesis until the critique file exists on origin.

If Labradorite is unavailable, fall back to a manual structured hypothesis job written by Grok, still one hyp only.

### Training wheels constraints (enforced)

- `continue_on_fail`: true only for pure measurement / scoreboard collection jobs.
- One hypothesis per job id.
- No max_steps / budget bump until a Labradorite (or equivalent) critique names `budget_exhaust` as the primary cause and proposes the exact new budget with justification.
- Prefer tool_runtime strategy. Record under train_gates.

## Dashboard E2E (fully functional requirement)

The agent page and `/api/host-agent` must expose the entire workflow end-to-end. Minimum panels / metrics:

| Panel / metric | Source | Purpose |
|----------------|--------|---------|
| Live status + heartbeat age | `artifacts/host_agent_status.json` | Liveness |
| Queue (pending / done / failed) | `artifacts/jobs/*` | FIFO truth |
| Last job envelope | `artifacts/host_agent_last_job.json` | Immediate result |
| Agent log tail | `artifacts/host_agent_log.txt` | Chronology |
| Foreman cursor + last playbook | `memory/host_agent/foreman_state.json` (or artifacts mirror) | Curriculum position |
| Apprentice lessons | `memory/ether_apprentice/lessons/*.json` | What ETHER has been taught |
| **RLHF health** | `preference_summary.json` + `assert_preferences_healthy` | Pairs, ranked_boosts, artifacts mirrored |
| **Ranked strategy boosts** | `live_strategy_boost` / summary | Policy signal |
| Recent scoreboards + traces | `artifacts/scoreboard*.json`, `trace_*.json` | Observability of runs |
| Critique backlog | `artifacts/critique_*.json` | Open root-cause work |
| Train gates / experience counts | vault sizes + doctrine_summary | Learning integrity |
| Gem registry health | registry.list_gems() + degraded | Clear Quartz / Labradorite / Amethyst ready |
| **LoRA readiness** | `artifacts/lora_train_last.json` + `lora_prep_summary` | Gated adapter status |
| **Introspection** | evolution_*.json | Four self-improvement questions answered |

Collector path rule is absolute: read what host_agent writes. Any divergence is a regression.

When revamping, keep the dark theme, monospace logs, and 1.5 s poll. Prefer additive panels over redesign that breaks existing muscle memory.

## Job formats

Prefer direct argv (never PowerShell path rewrite for Python):

```json
{
  "id": "p1_01_example",
  "note": "short purpose",
  "continue_on_fail": false,
  "steps": [
    {
      "argv": [".venv/Scripts/python.exe", "-m", "pytest", "tests/test_foo.py", "-q", "--tb=line"],
      "timeout": 300
    }
  ]
}
```

See `references/job-templates.md` for more templates (including Labradorite critique and RLHF tick).

## Path rules (never regress)

- Do not string-replace venv paths in PowerShell.
- host_agent resolves `.venv/Scripts/python.exe` argv to absolute under repo root.
- Prefer argv jobs over host_runner sprints for all Python work.
- git_push_report must include: last_job, status, pending/done/failed, scoreboard*.json, trace_*.json, strategy_stats.json, preference_summary.json, preferences_tail.jsonl, critique_*.json, lora_train_last.json, evolution_*.json.

## Apprentice model (Grok teaches ETHER)

| Path | Role |
|------|------|
| `memory/ether_apprentice/lessons/*.json` | Craft rules Grok writes; foreman loads every tick |
| `scripts/foreman.py` | Advances curriculum cursor; playbooks on FAIL match (guarded against infinity) |
| `scripts/ether_host.py` | One process: dashboard + agent + foreman |
| `core/train_gates.py` | Doctrine enforcement (code, not prompt) |
| `core/experience.py` | Vault record/retrieve gated by train_gates |
| `core/preference.py` | Offline RLHF from scoreboards → pairs + live_strategy_boost |

When teaching: push a lesson JSON (id, craft, rule, optional match/enqueue). ETHER applies it without waiting for chat. Primary goal is transferring operational judgment into the host.

### Lessons loaded (001–022+)

1–012 as previously established (git never stuck, argv only, FAIL→requeue, no placeholder, honest benchmarks, verified only PASS, reject leaky, prefer tool_runtime, no infra as code fail, report path hygiene, stage job dirs, auto-reload).

Additional critical lessons:

- **017–021** Safety / playbook recovery guards (no self-matching infinity)
- **022** Offline RLHF (scoreboard → preference pairs + boosts, infra filter, artifacts mirror)
- Future: Labradorite always-on critique, dashboard path hygiene, mid-job heartbeat, timeout push guarantee

## Training Doctrine (train_gates — mandatory)

`core/train_gates.py` + `core/experience.py` enforce four gates. **All training data must pass them.** Do not bypass.

### Gate 1 — Verified only PASS
```python
PASS_MIN_VERIFICATION = 0.99
may_record_pass(...): only if holdout_ok=True or (tests > 0 and ver >= 0.99)
```
Unverified successes (conf=1.0 theatre, zero tests) are rejected.

### Gate 2 — Reject leaky few-shot
On record, if holdout_test present → `prompt_guard.find_leaks(objective+code, holdout_test)`. Leak → do not store.

### Gate 3 — Prefer tool_runtime
```python
STRATEGY_TRUST = {
    "tool_runtime": 3.0,
    "multifile": 1.5,
    "with_asserts": 1.2,
    "default": 1.0,
    "agent_loop": 0.2,
    "best_of_n": 0.1,
}
```
`retrieve()` multiplies overlap by `strategy_boost(strategy)`. BoN / agent_loop are deprioritized.  
`live_strategy_boost` from preference.py further blends empirical win rate after enough samples.

### Gate 4 — No infra as code fail
`may_record_fail` rejects fail_kind in {dependency, plan, exception, infra, timeout_infra} and stderr signatures (docker daemon, ollama, connection refused, …). Only real code failures enter FAIL vault. Preference recording applies the same infra filter.

Doctrine summary available via `doctrine_summary()`. Every stored row carries `"train_doctrine": "grok_v1"`.

## Experience vault + Offline RLHF

- `memory/experience/pass.jsonl` — only gated successes
- `memory/experience/fail.jsonl` — only gated code failures
- Fingerprint dedup; rotate at 2000 rows
- `retrieve(objective, k=3)` ranks by overlap × strategy_boost + holdout/verification bonuses
- Preference pairs (same-mutation + cross) + `live_strategy_boost` + `dpo_rank_score` helper live in `core/preference.py`
- Artifacts mirrors (`preference_summary.json`, `preferences_tail.jsonl`, `strategy_stats.json`) are the only remote-visible learning signal

When enqueuing jobs that exercise experience/record, always include the train_gates validation path (e.g. `p3_02_train_gates`).

## Foreman curriculum (ordered)

Foreman walks `CURRICULUM` when pending empty.  

**Continuous z_gate loop is DISABLED** (2026-08-07) — it was producing an infinity enqueue once the curriculum finished. After the last curriculum item the host now stays idle. Re-enable later with a cooldown or mode flag if continuous verification is wanted.

On FAIL, `playbook_on_fail` matches lesson `match` regex against last job note/id and enqueues the lesson’s `enqueue` recovery job. Guarded by `_is_playbook_recovery` to prevent chaining.

Dashboard shows: foreman cursor, completed, lessons_n, last_playbook.

## Reading results (Grok)

Always fetch, never ask the user to paste logs:

- `artifacts/host_agent_last_job.json`
- `artifacts/host_report_latest.md` (if present)
- `artifacts/jobs/done/`, `artifacts/jobs/failed/`, `artifacts/jobs/pending/`
- `memory/host_agent/foreman_state.json` (local) + any artifacts mirror
- recent commits on `main` (`host agent report: job=...`)
- preference + scoreboard + critique artifacts

## Failure policy (updated)

1. Read report / last_job envelope + any scoreboard/trace that landed.
2. Classify with the taxonomy above. If unclear → enqueue Labradorite critique first.
3. Fix root cause on `main` in the same turn when possible.
4. Enqueue a new job id that implements the **smallest experiment** from the critique (never re-run the failed file still in `failed/`).
5. Do not stop the sprint to ask permission for the next obvious fix.
6. Classify infra vs code; only code failures feed experience FAIL vault and preference rejected side.

## Anti-patterns

- Asking the user to paste pytest output when a report was pushed
- Enqueueing one job and waiting for chat before the next
- PowerShell path rewrite of python.exe
- Leaving origin `core/tool_runtime.py` as the literal `placeholder`
- Reviving Best-of-N or flywheel push without honest benchmark evidence (FINDINGS)
- Recording unverified PASS or infra FAIL into the experience vault
- Ignoring train_gates when teaching or validating learning paths
- Globbing the entire `done/` or `failed/` directory on every `git_push_report` (causes WinError 206 once history grows)
- **Blind max_steps retries without Labradorite critique**
- **Dashboard reading memory/ paths while host writes artifacts/**
- Skipping GEMS on hard failures
- **Real LoRA / weight updates under training wheels without both promote flags**

## Repo anchors

- One-window host — `scripts/ether_host.py` + `scripts/start_ether_host.ps1`
- Agent — `scripts/host_agent.py`
- Foreman — `scripts/foreman.py`
- Train gates — `core/train_gates.py`
- Experience — `core/experience.py`
- Preference / offline RLHF — `core/preference.py`
- Lessons — `memory/ether_apprentice/lessons/`
- Queue — `artifacts/jobs/{pending,done,failed}/`
- Dashboard collector — `dashboard/collector_host_agent.py`
- Page — `dashboard/static/agent.html`
- Gems — `gems/{clear_quartz,rose_quartz,labradorite,amethyst,...}` + `core/registry.py`
- Docs — `docs/HOST_AGENT.md`, `docs/gems.md`, `docs/RLHF.md`, `docs/LOGIC_PATHS.md`

## Validation job (doctrine)

After any change to train_gates / experience / preference, enqueue:

```json
{
  "id": "p3_02_train_gates",
  "note": "unit test training doctrine gates",
  "steps": [
    {
      "argv": [".venv/Scripts/python.exe", "-m", "pytest", "tests/test_train_gates.py", "tests/test_preference_rlhf.py", "-q", "--tb=line"],
      "timeout": 120
    }
  ]
}
```

Only declare the training logic ready when this job is PASS and dashboard shows lessons ≥ 9 + foreman cursor advancing + preference health ok.

## Swarm / batch discipline

When user says “max swarm”, “batch process”, “do it all”, or “entire todo list”:

1. Produce a single ordered TODO with exact job ids and one-hyp notes.
2. Enqueue the first 3–5 under training wheels.
3. Read every report yourself.
4. On FAIL → Labradorite (or structured hyp) → fix → next batch.
5. Never leave the host idle with open root causes.

Keep training wheels on until a full Batch of hard mutations shows verified PASS with traces and healthy preferences on origin.

## GEM Evolution Framework (live 2026-08-08, v3)

Gems are agentic units. They run **separately** (host jobs) or as **one unit** via `core.evolution_loop.EvolutionController`.

### Closed loop entry points

```bash
# Full cycle (unit mode) — includes mandatory introspection
.venv/Scripts/python.exe -m core.evolution_loop

# LoRA data prep only (no weight updates)
.venv/Scripts/python.exe -m core.lora_prep

# LoRA readiness / dry-run (safe)
.venv/Scripts/python.exe -m core.lora_train
```

### Key artifacts written by the loop

| Path | Meaning |
|------|---------|
| `artifacts/evolution_<id>.json` | Full cycle report + introspection |
| `artifacts/critiques/critique_*.json` | Structured root_cause + smallest_experiment |
| `artifacts/lora_prep/preference_pairs.jsonl` | Gated pairs ready for Unsloth |
| `artifacts/lora_prep/success_sft.jsonl` | High-verification successes for SFT |
| `artifacts/lora_prep_summary.json` | Prep observability mirror |
| `artifacts/lora_train_last.json` | Dry-run or train report |
| `artifacts/lora_adapters/<id>/` | Adapter weights (only after promote flags) |
| `artifacts/langgraph_checkpoints/` | Persistent PlanState |

### Mandatory on non-infra FAIL

1. Call EvolutionController (or enqueue Labradorite job that produces structured critique).
2. Feed `smallest_experiment` into the next single-hypothesis job under training wheels.
3. Never budget-bump or multi-hyp until Labradorite has spoken.

### LangGraph

Optional (`ETHER_LANGGRAPH=1`). PlanState now carries last_critique + hypothesis + root_cause + severity + introspection + thread_id. File checkpoint. Introspect node forces the four self-improvement questions. Still falls back to rule planner. Not a full agent runtime — synergistic state only.

### LoRA

Data prep is live. Weight updates are **gated**. Sequence: clean preference data → dashboard green → dry_run green → `ETHER_LORA_TRAIN=1` + `ETHER_LORA_PROMOTE=1` → adapter → Citrine memory → human/holdout gate → load behind feature flag in Rose Quartz.

See `docs/GEM_EVOLUTION.md` for the full schema.
