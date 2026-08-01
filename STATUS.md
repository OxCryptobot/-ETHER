# @ETHER Status

**Updated:** 2026-08-01 — Phase D tool-path measured on host.

Read `docs/FINDINGS.md` before changing anything. Three days of measurement are
in it and the mistakes are expensive to repeat.

---

## Where the project actually is

| | |
|---|---|
| Tests | **763** (was 48) |
| Verification | held-out grading, mutation score 0.966 |
| Leak channels closed | **7** |
| `main` | green, and green on a fresh clone |
| **Does ETHER beat a bare model on holdout generate?** | **No** (ablation stands) |
| **Does tool-runtime beat bare on hard repo-oracle pack?** | **Yes** (Phase D) |

### Holdout generate (unchanged — still the honest generate ceiling)

| model | bare | bare+sys | ether |
|---|---|---|---|
| `qwen3.6:35b-a3b` | 0.933 | — | 0.874 |
| `qwen2.5:3b` | 0.317 | 0.333 | 0.292 |

`ether − bare+sys = −0.042`, McNemar p = 0.22. Data: `docs/results/ablation_qwen2.5-3b_clean.json`.
Agent loop remains net negative. **Any pre-audit conf=1.000 is void.**

### Phase D — hard repo-oracle pack (host `qwen3.5:4b`)

Task class: fix broken multi-file packages; oracle = project pytest (not holdout text).

| arm | hard 5 (lru/merge/ledger/topo/intervals) |
|-----|------------------------------------------|
| **direct** (ToolRuntime only) | **5/5** |
| **pipeline** (Pipeline + tools + workspace verify, max_steps=16) | **5/5** |
| **bare** (Pipeline, tools off) | **0/5** |

Confounders fixed before claiming pipeline 5/5: batch now loads `.env` (was stuck on Rose default `qwen2.5-coder:3b`); `--max-steps` is honored (was clamped to 12). Ledger/topo failed under 3b/12 and passed under 4b/16.

Scope: this is **not** a claim that generate-side ETHER beats bare on HumanEval-style holdouts. It is evidence that **Observe→Act→Observe tools** clear repo-grounded fix tasks where bare generate does not.

### Why more generation-side work is capped

Oracle pass@3 is the ceiling *any* selector could reach:

| arm | pass@1 | oracle pass@3 | headroom |
|---|---|---|---|
| `bare+sys` | 0.342 | 0.400 | **+0.058** |

A perfect, infallible selector gains 5.8 points. **Do not spend a week
optimising the selector.**

---

## What genuinely works

- **`core/holdout.py`** — grades against unseen assertions; strips the model's
  own asserts so they cannot preempt; requires a sentinel so `sys.exit(0)`
  cannot fake a pass.
- **`core/prompt_guard.py`** — catches leaks by inspecting the finished prompt
  rather than remembering channels. Found 3 of the 7.
- **`core/assert_audit.py`** — counts only assertions that could actually fail.
- **`scripts/ablation.py`** — seeded, resumable, aborts at >25% errors, prints
  its own minimum detectable effect before running.
- **Sandbox** — hardened, fails closed, `uid 65534`, all capabilities dropped.
- **Tool runtime + Clear Quartz workspace verify** — Phase D hard pack 5/5
  pipeline / 0/5 bare on host 4B.

The asymmetry worth building on: this system is far better at saying **"this is
wrong"** than at producing something right — and tools let it *act* on that.

---

## Where to go next

**Phase D pack is measured.** Next leverage is broader repo-grounded tasks
(real projects, not only five fixtures), still judged by the package's own
tests. Do not revive best-of-N / curriculum / flywheel without a new positive
measurement.

Holdout generate remains a weak arm — do not spend cycles on selector polish
(oracle pass@3 headroom ~5.8pp).

---

## Running it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # ETHER_PRIMARY_MODEL must match `ollama list`

pytest -q
python -m cli.main doctor

# Phase D batch (host)
python -m scripts.batch_phase_d --arm pipeline --mode live --tier hard --max-steps 16 --timeout 500
```

## Hazards

- **A red `main` kills the other machine** — `pytest` is a static gate in the
  flywheel. Use `pytest && git push` as one command.
- **The flywheel is a third writer** — set `ETHER_FLYWHEEL_PUSH=0` while collaborating.
- **`ETHER_WARM_SANDBOX` stays off**.
- Prefer `ETHER_SANDBOX_BACKEND=docker` wherever Docker exists.
- Measure scripts must `load_dotenv` or Rose falls back to `qwen2.5-coder:3b`.
