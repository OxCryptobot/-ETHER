# @ETHER Task Board

**Updated:** 2026-07-26T02:10Z · **HEAD:** main (flywheel healthy)

---

## Done

### Batch 1 — Pipeline intelligence
| # | Task | Notes |
|---|------|-------|
| 1 | `tool_assist` few_shot_pack before code | `ETHER_TOOL_ASSIST=1` |
| 2 | `save_success_pattern` on sandbox PASS | memory/learning |
| 3 | `secret_scan` + `subprocess_audit` pre-audit | lowers conf if dirty |

### Batch 2 — Tools, plan intents, learning surface
| # | Task | Notes |
|---|------|-------|
| 4 | Dashboard tools + fabricate log data | collector snapshot |
| 5 | Selenite tool intents (`run` / `fabricate` / `generate`) | regex + available_tools |
| 6 | Fail-streak → opt-in auto-fabricate | `ETHER_AUTO_FABRICATE_ON_FAIL` |
| 9 | `ether learn-stats` | bandit + fail streak |

Also complete earlier: fabricate loop, persistent tool catalog, flywheel gates, learning bandit.

---

## Active — Batch 3 (next 10)

| # | Priority | Task | Owner surface |
|---|----------|------|----------------|
| 11 | P0 | Benchmark harness (`scripts/bench.py` + sample suite) | QA |
| 12 | P1 | Rose Quartz token streaming → CLI | generate |
| 13 | P0 | Dashboard promote API (one-click quarantine→persistent) | extend/UI |
| 14 | P0 | Execute Selenite `action:run` tool_request mid-pipeline | pipeline |
| 15 | P1 | Index PASS patterns into Citrine | memory |
| 16 | P1 | Flywheel report includes learn-stats snapshot | autonomy |
| 17 | P1 | `repo_map` in tool_assist for multi-file objectives | plan/context |
| 18 | P0 | Fabricate AST validation (`main` + compile) | grandidierite |
| 19 | P2 | Dashboard WS actions (promote / fabricate triggers) | UI |
| 20 | P2 | v0.2.0 VERSION + release notes | release |

---

## Deferred / not started (from earlier backlog)

| # | Task | Why deferred |
|---|------|----------------|
| 7 | Formal HumanEval-style suite | Folded into #11 |
| 8 | Streaming (same as #12) | Renumbered |
| 10 | Promote UX | Split into #13 + #19 |

---

## Suggested order of attack

1. **#18** — harden fabricate (cheap, safety)
2. **#14** — run-tool path in pipeline
3. **#13** — promote API
4. **#11** — bench harness
5. **#17 → #15 → #16** — context/memory/autonomy polish
6. **#12, #19, #20** — UX + release

---

## Env flags (reference)

```env
ETHER_TOOL_ASSIST=1
ETHER_LEARNING=1
ETHER_AUTO_PROMOTE=0
ETHER_AUTO_FABRICATE_ON_FAIL=0
ETHER_FAIL_STREAK_THRESHOLD=3
ETHER_FABRICATE_STUB_ONLY=0
```
