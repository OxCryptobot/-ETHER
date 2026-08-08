# ETHER Logic Paths (Teacher → Apprentice)

This document is the **decision procedure** the teacher uses when fixing the host.
ETHER must internalize the path, not just the final patch.

## Path: FAIL → Fix (primary)

```
FAIL observed
    │
    ├─ Read evidence (last_job, scoreboard, stderr)     [observe]
    │
    ├─ Classify                                         [reason]
    │     A budget-not-yet-measured
    │     B budget-ruled-out (same fail @ 2 budgets)
    │     C tool/order gap
    │     D repair quality
    │     E infra (never vault as code fail)
    │
    ├─ One hypothesis only                              [commit]
    │
    ├─ Smallest job that tests it                       [act]
    │     new id · one mutation · one lever · trace on
    │
    ├─ Wait for scoreboard on origin                    [observe]
    │
    ├─ Hypothesis true?                                 [reason]
    │     yes → write lesson (no self-match enqueue)
    │     no  → back to classify with new letter
    │
    └─ NEVER chain playbook recoveries                  [safety]
```

## Path: Playbook safety

```
playbook_on_fail
    │
    ├─ last_job.ok is False?
    │     no → return
    │
    ├─ is recovery already? (note starts with playbook:
    │    or id has diag_after_ / ledger_trace / topo_trace)
    │     yes → return (do not chain)
    │
    └─ match lesson → enqueue ONCE with note=playbook:...
```

## Path: Preference / ML signal

```
clean scoreboard lands
    │
    ├─ record_preferences_from_scoreboard
    │     pass pairs preferred over fail
    │     higher verification preferred
    │
    └─ mirror strategy_stats → artifacts/ (observable)
```

## What not to do

| Anti-pattern | Why |
|--------------|-----|
| Raise max_steps again after two identical max_steps fails | Budget ruled out; wastes queue |
| Playbook that matches its own recovery | Infinity loop |
| Ask human to paste logs | Host pushes artifacts; read them |
| Record infra timeout as code FAIL | Pollutes experience vault |
| Multiple hypotheses in one job | Uninterpretable scoreboard |

## Current open hypotheses (Phase E hard class)

- ledger_no_debit / ledger_double_total / topo_drop_cycle_raise still fail under `--read-first` at steps 24–40.
- Next lever: **C or D** (tool order forced, or decide/repair quality), not budget.
- Need: actual tool-call trace on origin before the next policy change.

Taught by Grok 2026-08-08. Lessons 017–021 encode the same rules for the foreman.
