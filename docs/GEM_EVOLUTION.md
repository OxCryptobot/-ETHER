# GEM Evolution Architecture — Executable Schema

**Status:** live framework (2026-08-08)  
**Doctrine:** offline RLHF first → structured critique → optional LoRA later  
**Training wheels:** ON by default

## Core Principle

The eight gems are agentic units. They can run **separately** (host jobs, CLI, tests) or as **one unit** via `core.evolution_loop.EvolutionController`.

No gem owns the entire brain. The closed loop is the brain.

## Role Contracts (non-overlapping)

| Gem | Responsibility | Skip condition |
|-----|----------------|----------------|
| Selenite | Plan + hypothesis from lessons | Never on new task |
| Rose Quartz | Generate / repair under controlled sampling | Never when generation required |
| Clear Quartz | Isolated execution + score | Never for verification |
| Black Tourmaline | Security audit | Measurement-only mode |
| Labradorite | Structured root_cause + smallest_experiment | **Never on FAIL under training wheels** |
| Citrine | Persist / retrieve memory | Soft degrade only |
| Amethyst | Log + evolution signal | Never for observability |
| Grandidierite | Tool fabricate only on explicit request | Default skip |

## Closed Loop (Infinity Evolution Loop v2)

```
TRIGGER (Pipeline FAIL | Host FAIL | explicit tick)
  → Selenite (plan + hyp from memory bus)
  → Rose Quartz (candidate)
  → Clear Quartz (score)
  → Black Tourmaline (audit)
  → Labradorite (MANDATORY structured critique)
  → Citrine + memory_bus (persist)
  → Amethyst (signal)
  → preference.py (offline RLHF pairs + live_strategy_boost)
  → [optional] Grandidierite if tool missing
  → gate (train_gates) → next cycle or promote
```

Entry points:
- `python -m core.evolution_loop`
- `EvolutionController().run_cycle(...)`
- Host job that calls the same

## LangGraph State (minimal, synergistic)

`gems/selenite/graph.py` PlanState now carries:
- `last_critique`
- `hypothesis`

Still optional (`ETHER_LANGGRAPH=1`). Falls back to rule planner. No heavy runtime yet.

## LoRA Data Prep (ready, no training)

```bash
python -m core.lora_prep
```

Produces:
- `artifacts/lora_prep/preference_pairs.jsonl`
- `artifacts/lora_prep/success_sft.jsonl`
- `artifacts/lora_prep_summary.json`

Gated by min_gap, non-infra, holdout_ok, train_doctrine.  
**Weights are never updated by this module.**

Future (only after clean data + dashboard green):
1. Unsloth QLoRA script (optional extra)
2. Adapter load path in Rose Quartz behind feature flag
3. Human / holdout approval before promotion

## Host Integration

On non-infra FAIL the host path must:
1. Enqueue or call `EvolutionController` (or Labradorite job)
2. Write `artifacts/critiques/critique_*.json`
3. Feed `smallest_experiment` into the next single-hypothesis job

Dashboard must surface:
- last critiques (root_cause, confidence)
- ranked_boosts
- lora_prep_summary
- evolution_*.json

## Anti-patterns

- Running LoRA before preference data is clean
- Skipping Labradorite on max_steps / verification FAIL
- Treating LangGraph skeleton as full agent state runtime
- Mixing infra failures into preference pairs
- Budget bumps under training wheels without measured root cause
