# @ETHER Status

**Updated:** 2026-07-29 — post-audit, measured.

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
| **Does ETHER beat a bare model?** | **No** |

### The headline measurement

| model | bare | bare+sys | ether |
|---|---|---|---|
| `qwen3.6:35b-a3b` | 0.933 | — | 0.874 |
| `qwen2.5:3b` | 0.317 | 0.333 | 0.292 |

`ether − bare+sys = −0.042`, McNemar p = 0.22, 360 samples, zero leaks.
Data: `docs/results/ablation_qwen2.5-3b_clean.json`.

The agent loop (`ETHER_AGENT_LOOP=1`) was built and measured too: **0.083 vs
0.333**. It works mechanically — draws N candidates, scores them, selects the
best, never regresses — it just does not help.

**Any earlier number is void.** Every `conf=1.000` in the history predates
honest grading, and a `+53pp` result committed on 2026-07-29 was retracted the
same night as contamination.

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

The asymmetry worth building on: this system is far better at saying **"this is
wrong"** than at producing something right.

---

## Where to go next

**Repo-grounded tasks.** Apply a change to an existing file and verify with the
repository's own test suite. The bare model scores near zero there, so the
headroom is real — and the repo's tests are an oracle that *cannot* be leaked
into a prompt, because they are run rather than shown.

---

## Running it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # ETHER_PRIMARY_MODEL must match `ollama list`

# memory/ is gitignored — benchmark datasets are LOCAL artifacts:
python scripts/build_headroom.py
python scripts/build_calibrated.py

pytest -q                     # 763 passing
python -m cli.main doctor
python -m cli.main run "write a python function is_even(n), with asserts"
```

Measure a change:

```bash
python scripts/ablation.py --dry-run --no-probe          # plan + cost, no GPU
python scripts/ablation.py --bare-strip-preamble --no-learning
```

## Hazards

- **A red `main` kills the other machine** — `pytest` is a static gate in the
  flywheel. Use `pytest && git push` as one command. This bit us three times.
- **The flywheel is a third writer** — it pushes to `main` on a timer. Set
  `ETHER_FLYWHEEL_PUSH=0` while collaborating.
- **`ETHER_WARM_SANDBOX` stays off** — shares `/tmp` across programs, buys 0.67%.
- Prefer `ETHER_SANDBOX_BACKEND=docker` wherever Docker exists; `local` runs
  model-authored code on the host with no isolation.
