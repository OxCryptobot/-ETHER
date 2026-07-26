# @ETHER Methodology (transparent)

## What this system is

A **local-first verified coding loop**: plan → retrieve experience → generate (local LLM, optional cloud burst) → assert harness → Docker sandbox → audit → gate → learn.

It is **not** a claim of AGI, formal proof, or superiority over Cursor/Claude Code/Aider without published numbers.

## Hardware profile (authoritative for claims)

- GPU class: GTX 1650 4GB class / ~12GB RAM (typical laptop)
- Primary local model: `qwen2.5-coder:3b` (or whatever `ETHER_PRIMARY_MODEL` is set to)
- Sandbox: Docker `python:3.12-slim`, no network

## Scoreboard metrics

| Metric | Meaning |
|--------|---------|
| **Bench pass_rate** | Fixed regression tasks (`scripts/bench.py`) |
| **Quiz holdout pass_rate** | Tasks **never** used as flywheel curriculum (`scripts/quiz.py`) |
| **Curriculum tier** | Difficulty band after vault-synced wins |
| **Guardian frozen** | True if bench regresses beyond tolerance |
| **Burst calls** | Count of cloud specialist invocations |

## Honesty rules

1. Print-only success ⇒ `total_tests=0` ⇒ verification soft-cap (no fake conf=1.0 from prints alone).
2. Holdout quiz IDs excluded from curriculum sampling.
3. Cloud burst (`ETHER_BURST=1`) never bypasses sandbox/audit.
4. Marketing language avoided in scoreboard; numbers only.

## Reproduce

```powershell
python scripts/bench.py --fast
python scripts/quiz.py --limit 5
python scripts/reconcile_tools.py
Get-Content SCOREBOARD.md
```

## Burst setup (optional titan)

```powershell
$env:ETHER_BURST = "1"
$env:ETHER_BURST_URL = "https://api.x.ai/v1"
$env:ETHER_BURST_MODEL = "grok-3"
$env:ETHER_BURST_API_KEY = "xai-..."
$env:ETHER_BURST_MAX_CALLS = "40"
```
