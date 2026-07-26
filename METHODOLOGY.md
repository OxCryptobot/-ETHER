# @ETHER Methodology (transparent)

## What this system is

A **local-first verified coding loop**: plan → retrieve experience → generate (local LLM, optional cloud burst) → assert synthesis → Docker sandbox → audit → gate → learn.

It is **not** a claim of AGI, formal proof, or superiority over Cursor / Claude Code / Aider / Continue without published numbers on a fixed suite.

## Hardware profile (authoritative for claims)

- GPU class: GTX 1650 4GB class / ~12GB RAM (typical laptop)
- Primary local model: whatever `ETHER_PRIMARY_MODEL` is (e.g. `qwen2.5-coder:3b`)
- Sandbox: Docker `python:3.12-slim`, no network

## Scoreboard metrics

| Metric | Meaning |
|--------|---------|
| **Bench pass_rate** | Fixed regression (`scripts/bench.py`, prefer `--fast` often) |
| **Quiz holdout pass_rate** | Tasks never used as flywheel curriculum (`scripts/quiz.py`) |
| **Curriculum tier** | Difficulty band after vault-synced wins |
| **Guardian frozen** | True if bench regresses beyond tolerance |
| **Burst calls** | Cloud specialist invocations |

## Honesty rules

1. Print-only success ⇒ `total_tests=0` ⇒ verification soft-cap.
2. Holdout quiz IDs excluded from curriculum sampling.
3. Cloud burst never bypasses sandbox/audit.
4. Process rewards prefer first-compile + asserts; burst has a small cost.
5. Patches only under `memory/scratch` (no silent repo mutation).

## Side-by-side protocol (vs Aider / Continue / Cursor agent)

**Purpose:** honest comparison, not marketing.

1. Fix a **holdout set** of 10 tasks (from `memory/quizzes/holdout_v1.json`).
2. Same machine, same wall-clock window policy (e.g. 3 min cap / task).
3. For each tool, record: pass/fail, latency, human edits required (0/1), files touched.
4. @ETHER rules: no manual code edit mid-task; only `ether run` / pipeline.
5. Publish a table in `SCOREBOARD.md` or a dated `memory/bench/compare_YYYYMMDD.md`:

| Task id | ETHER | Aider | Continue | notes |
|---------|-------|-------|----------|-------|
| h01 | | | | |

6. Do **not** claim winners without that table.

## Reproduce

```powershell
python scripts/bench.py --fast
python scripts/quiz.py --limit 5
python scripts/reconcile_tools.py
Get-Content SCOREBOARD.md
```

## Burst setup (optional)

```powershell
$env:ETHER_BURST = "1"
$env:ETHER_BURST_URL = "https://api.groq.com/openai/v1"  # or https://api.x.ai/v1
$env:ETHER_BURST_MODEL = "llama-3.3-70b-versatile"
$env:ETHER_BURST_API_KEY = "..."   # local only
$env:ETHER_BURST_ON_FAIL = "1"
```
