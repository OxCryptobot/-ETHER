---
name: super-auditor
description: Rigorous senior engineering audit of ETHER. Use for robustness reviews, scale readiness, architecture assessment, competitive gap analysis, or when user says audit, super-auditor, engineering assessment, maturity score, or SOTA.
metadata:
  version: "2.0"
---

# Super-auditor (ETHER) v2

Assume the system works and underperforms. Expose why. Do not defend implementations. Do not lift wheels from the audit. Do not soften the verdict.

## Grounding (mandatory)

Read GitHub OxCryptobot/-ETHER at HEAD, not memory of a prior chat. Current audit HEAD: `9aa1865`.

Must cite:
- docs/FINDINGS.md (ether <= bare; agent_loop 0.083 vs 0.333; 148x live)
- artifacts/eligible_rates.json vs raw honest_live_rates.json
- artifacts/scoreboard_p3_25_merge.json (playbook PASS is not model skill)
- core/pipeline.py size; Rose vs multi_llm default models
- ETHER_* flag count vs .env.example
- SEED_DENY in core/live_fixture_policy.py
- core/checkpoint.py “Not fully wired into Pipeline yet”
- core/evolution_loop.py hardcoded four-question answers

## 20 subsystems

Architecture, prompt stack, agent loop, planning, context, tools, file editing, repo intelligence, memory, reflection, subagents, hooks, provider, UX, performance, reliability, security, evaluation, missing capabilities, competitive gap.

## Per issue

Severity, impact, likelihood, root cause, failure scenario, fix, difficulty, expected improvement, priority, engineering time.

## Scores (recompute each audit)

Score 0-10: architecture, tool-first, measurement honesty, autonomy, planning, memory, security, UX, live performance, vs Claude Code.

2026-08-29 baseline: 4 / 6 / 8 / 3 / 3 / 5 / 6 / 5 / 2 / 2. Overall product ~4.4. Harness honesty ~7. Living agent ~2.8.

Living-agent claim remains refused until unaided merge+ledger LIVE ×3.

## Output

Write docs/AUDIT_SOTA_<date>.md. Update goal plus keep-pushing if doctrine moved.

## Modes

full | focused:<subsystem> | risk | light-self.
