# @ETHER — audit record

What was audited, how, and what it found. Companion to `docs/FINDINGS.md`
(the findings) and `docs/COWORK.md` (the changes).

**Period:** 2026-07-27 → 2026-07-29. **Method:** multi-agent parallel audits with
adversarial verification — every high-severity claim was handed to a separate
reviewer whose default was that the claim was wrong, already fixed, or inflated.

---

## Audits run

| # | Scope | Agents | Outcome |
|---|---|---|---|
| 1 | Silent failures in `core/` + `gems/` | 1 | 19 findings; sandbox host-fallback, `_embed` zero-vector sentinel |
| 2 | Confidence & gating honesty | 1 | **Verification was theatre** — 12 adversarial artifacts all scored 1.000 |
| 3 | Security: sandbox, fabrication, push | 1 | Host RCE via `patch_loop`; quarantine enforced nothing |
| 4 | Test-coverage gaps | 1 | `pytest` mutating production state; 61% of run history was test artifacts |
| 5 | Whole-`core/` enterprise audit | **60** | 60 findings confirmed, **22 rejected** as wrong/already-fixed |
| 6 | Fix waves (pipeline, sandbox, health, infra) | 4 | Every open finding from #1–5 |
| 7 | Design defects (bandit, benchmarks) | 2 | Bandit statistically empty; benchmarks measured transcription |

---

## What made the audits work

**Adversarial verification.** In audit #5, **22 of 82 findings were rejected** —
unreachable code, already fixed, or an impact that did not follow. A plausible
finding that does not survive contact with the code is worse than no finding,
because it gets acted on.

**Running the arm expected to show nothing.** The `ether-no-repair` arm came back
*bit-identical* to `ether` (105/120 each, p=1.0). That impossible result exposed
the seventh leak channel — repair cannot matter when the answer is already in
the prompt. **The null result found what the positive result concealed.**

**Mechanical checks over reasoning.** Six of seven leak channels were found by
`core/prompt_guard.py` inspecting a finished prompt, not by reasoning about
which channels exist. Reasoning found one; the guard found the rest.

**Fresh-clone verification.** Cloning to `/tmp` and running the suite caught a
`NameError` that only fires when a gitignored dataset is absent — invisible on
the machine that wrote it, fatal on any other.

---

## Findings the audits produced

Ranked by how badly they misled:

1. **Verification measured "the process exited 0".** A no-op function, an
   assert in a comment, a false assert swallowed by `except`, and a printed
   `"42 passed"` all scored **1.000**; honest code reporting a real failure
   scored 0.26. The metric rewarded concealment and fed the reward, the
   curriculum and the commit gate.
2. **Seven leak channels.** Curriculum, bench prompts, `hidden_quiz`, BM25 over
   `scripts/`, two memory stores, and retrieval serving prior *solutions*.
3. **Three safety flags gated nothing** — `ETHER_FLYWHEEL_PUSH`,
   `ETHER_AUTO_PROMOTE`, `ETHER_AUTO_MODEL`.
4. **The model ran at `presence_penalty=1.5`** for the project's entire life —
   close to worst-case sampling for code.
5. **The guardian ratcheted its own baseline down** — 0.95 → 0.41 without
   freezing, each step "within tolerance".
6. **Docker backend silently ran code on the host** when Docker was missing.
7. **Difficulty is bimodal** — 15 of 78 authored tasks land where a scaffold
   could show anything; aiming at the middle made it *worse*.

---

## Audits of our own work

Three defects were found in fixes written during this session:

- `count_real_asserts` initially counted assertions in never-called functions.
- `grade_against_holdout` was bypassable by `sys.exit(0)` — exit code alone was
  never proof the assertions ran.
- The curriculum leak fix covered `tiers.json` but not the `scratch_tier.json`
  that `load_tiers()` splices in at runtime, and the guarding test read the
  wrong file.

Each was found by auditing the fix rather than trusting it. That is the habit
worth keeping.

---

## How to run one

```bash
pytest -q                                            # 763 tests
python scripts/ablation.py --dry-run --no-probe      # plan, no GPU
python scripts/build_headroom.py --verify-only       # 60 sandbox grades
python -m cli.main doctor
```

Then delete `memory/quizzes/*.json` and run `pytest` again — it must exit 0.
That is the check that keeps the other machine in the loop.
