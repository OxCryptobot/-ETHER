---
name: host-agent-live
description: Drive ETHER host agent job queue on the Windows GPU host via GitHub pending jobs, reports, and dashboard. Use when user says host agent live, host agent, job queue, pending jobs, sprint delivery, batch host, ether_host, foreman, train gates, or asks to run work on their machine without pasting logs. Also use for dashboard revamps, GEMS engagement on FAIL, RLHF observability, and E2E workflow diagnosis.
metadata:
  version: "3.1"
---

# Host Agent Live (v3.1 — living-agent lock)

## v3.1 lock (SOTA audit 2026-08-29)

- Training wheels stay ON. Do not lift `ETHER_SOFT_LAUNCH` from this skill.
- Playbook PASS ≠ living agent. Label `teacher_playbook`. p3_25 merge 1.0 does **not** increment the gate.
- Living-agent gate: unaided merge+ledger LIVE ×3 with `replace_once` from `bug_comments`, no fixture dictionary, no global spoilers.
- `core/evolution_loop.py` four questions are hardcoded theatre. Do not treat `evolution_*.json` answers as model insight.
- `AUTONOMY.md` “code loop is closed” is the daemon watchdog, not coding-agent autonomy.
- `last_job` is completed-truth. Never ask the user to paste logs. Never ask the user to watch the dashboard.
- Labradorite from traces, not line counts. One hypothesis per job. New job id. Never requeue the failed file.
- Eligible 1.0 is greeter/wallet. Hard pack is SEED_DENY.

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

**On every code FAIL (training wheels):** Labradorite critique job → `root_cause` + `smallest_experiment` → one new job id. Never blind max_steps retries. Playbook PASS is teacher skill.

### Training wheels constraints (enforced)

- `continue_on_fail`: true only for pure measurement / scoreboard collection jobs.
- One hypothesis per job id.
- No max_steps / budget bump until a Labradorite critique names `budget_exhaust`.
- Prefer tool_runtime strategy. Record under train_gates.

## Anti-patterns (v3.1)

- Asking the user to paste pytest output when a report was pushed
- Blind max_steps retries without Labradorite critique
- Treating evolution_loop introspection as model self-improve
- Claiming living-agent on playbook PASS or eligible 1.0
- Dashboard reading memory/ paths while host writes artifacts/
- Real LoRA / weight updates under training wheels without both promote flags
- Globbing the entire done/ or failed/ directory on every git_push_report

## Repo anchors

- One-window host — `scripts/ether_host.py` + `scripts/start_ether_host.ps1`
- Agent — `scripts/host_agent.py`
- Foreman — `scripts/foreman.py`
- Train gates — `core/train_gates.py`
- Experience — `core/experience.py`
- Preference / offline RLHF — `core/preference.py`
- Queue — `artifacts/jobs/{pending,done,failed}/`
- Docs — `docs/HOST_AGENT.md`, `docs/AUDIT_SOTA_2026-08-29.md`
