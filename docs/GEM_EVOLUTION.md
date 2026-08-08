# GEM Evolution Architecture — Executable Schema v3

**Status:** live framework (2026-08-08)  
**Doctrine:** offline RLHF first → structured critique → mandatory introspection → optional gated LoRA  
**Training wheels:** ON by default (see definition below)

## What Are Training Wheels?

Training wheels are the **default operating mode** of ETHER until explicitly lifted by the operator.

They are not a soft suggestion. They are code + host policy:

| Rule | Enforcement |
|------|-------------|
| One hypothesis per job / cycle | EvolutionController + host job ids |
| Labradorite structured critique on every non-infra FAIL | Mandatory before next experiment |
| No max_steps / budget bump until measured `budget_exhaust` | train_gates + Labradorite |
| Preference pairs + experience vault reject infra + unverified PASS | `core/train_gates.py` + `preference.py` |
| LoRA / weight updates never automatic | `core/lora_train.py` requires `ETHER_LORA_TRAIN=1` **and** `ETHER_LORA_PROMOTE=1` |
| continue_on_fail only for pure measurement | Host agent |
| Continuous z_gate loop disabled | Foreman |

Lift only after a full batch of hard mutations shows verified PASS + healthy preferences on origin.

## Core Principle

The eight gems are agentic units. They can run **separately** (host jobs, CLI, tests) or as **one unit** via `core.evolution_loop.EvolutionController`.

No gem owns the entire brain. The closed loop is the brain.

**The system always asks itself:**

1. How do we get better?
2. How do we self-improve?
3. How can I surpass my limitations?
4. What do I need to do?

These questions are hard-coded into EvolutionController and the LangGraph introspect node. Answers are recorded. Creative discovery stays inside the gates. **Never unrestricted self-modification.**

## Role Contracts (non-overlapping)

| Gem | Responsibility | Skip condition |
|-----|----------------|----------------|
| Selenite | Plan + hypothesis from lessons + LangGraph state | Never on new task |
| Rose Quartz | Generate / repair under controlled sampling | Never when generation required |
| Clear Quartz | Isolated execution + score | Never for verification |
| Black Tourmaline | Security audit | Measurement-only mode |
| Labradorite | Structured root_cause + smallest_experiment | **Never on FAIL under training wheels** |
| Citrine | Persist / retrieve memory (incl. adapter metadata) | Soft degrade only |
| Amethyst | Log + evolution signal | Never for observability |
| Grandidierite | Tool fabricate only on explicit request | Default skip |

## Closed Loop (Infinity Evolution Loop v3)

```
TRIGGER (Pipeline FAIL | Host FAIL | explicit tick)
  → SELF INTROSPECT (four questions — always)
  → Selenite (plan + hyp from memory bus + LangGraph checkpoint)
  → Rose Quartz (candidate)
  → Clear Quartz (score)
  → Black Tourmaline (audit)
  → Labradorite (MANDATORY structured critique on FAIL)
  → Citrine + memory_bus (persist lesson + adapter memory)
  → Amethyst (signal)
  → preference.py (offline RLHF pairs + live_strategy_boost)
  → lora_train.dry_run_report (readiness only)
  → [optional] Grandidierite if tool missing
  → gate (train_gates) → next cycle or promote
```

Entry points:

```bash
# Full cycle (unit mode)
.venv/Scripts/python.exe -m core.evolution_loop

# LoRA data prep only (no weight updates)
.venv/Scripts/python.exe -m core.lora_prep

# LoRA train readiness / dry-run (safe under wheels)
.venv/Scripts/python.exe -m core.lora_train
```

## LoRA / PEFT / Unsloth (gated)

`core/lora_train.py` expands the classic pattern:

```python
import loralib as lora
layer = lora.Linear(in_features=..., out_features=..., r=16)
lora.mark_only_lora_as_trainable(model)
torch.save(lora.lora_state_dict(model), "adapter.pth")
```

into a professional path:

1. **Data** — `lora_prep` produces preference_pairs.jsonl + success_sft.jsonl (already live)
2. **Dry-run** — always available; reports readiness, recommended rank, VRAM notes
3. **Train** — only when `ETHER_LORA_TRAIN=1` **and** `ETHER_LORA_PROMOTE=1`
4. **Adapter only** — base model never overwritten; lands in `artifacts/lora_adapters/<id>/`
5. **Citrine memory** — every successful adapter is embedded so the system can later recall "what this adapter improved"
6. **Backend order** — Unsloth → PEFT → loralib → torch_manual (detected at runtime)

Hardware lock (GTX 1650 4GB): rank ≤ 16, target modules limited, max_steps tiny under wheels.

## LangGraph State (self-evolving)

`gems/selenite/graph.py`:

- **PlanState** carries `last_critique`, `hypothesis`, `root_cause`, `severity`, `introspection`, `thread_id`
- **Persistent checkpoint** under `artifacts/langgraph_checkpoints/<thread_id>.json`
- **Introspect node** forces the four questions every plan
- **Conditional severity** — high root_cause inserts Labradorite first
- **Tool stubs** for Clear Quartz / Grandidierite (host executes)
- **Evolve intent** — special plan path for self-improvement cycles
- Still optional (`ETHER_LANGGRAPH=1`); falls back to rule planner

Not a full multi-agent swarm runtime. Synergistic state that survives turns and feeds the evolution loop.

## Key Artifacts

| Path | Meaning |
|------|---------|
| `artifacts/evolution_<id>.json` | Full cycle report (incl. introspection) |
| `artifacts/critiques/critique_*.json` | Structured root_cause + smallest_experiment |
| `artifacts/lora_prep/*.jsonl` | Gated pairs / SFT ready for Unsloth |
| `artifacts/lora_prep_summary.json` | Prep observability |
| `artifacts/lora_train_last.json` | Last dry-run or train report |
| `artifacts/lora_adapters/<id>/` | Adapter weights + meta (only after promote) |
| `artifacts/langgraph_checkpoints/` | Persistent PlanState |

## Host Integration

On non-infra FAIL the host path must:

1. Call or enqueue EvolutionController (or Labradorite job)
2. Write `artifacts/critiques/critique_*.json`
3. Feed `smallest_experiment` into the next single-hypothesis job under training wheels
4. Surface introspection + lora dry-run on dashboard

## Anti-patterns

- Running real LoRA before preference data is clean and flags are set
- Skipping Labradorite on max_steps / verification FAIL
- Treating LangGraph as full agent runtime
- Mixing infra failures into preference pairs
- Budget bumps under training wheels without measured root cause
- Unrestricted self-modification or auto-promote of adapters
- Ignoring the four self-improvement questions
