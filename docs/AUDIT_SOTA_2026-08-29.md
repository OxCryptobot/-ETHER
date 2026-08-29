# ETHER SOTA engineering audit — 2026-08-29

**Repo:** [OxCryptobot/-ETHER](https://github.com/OxCryptobot/-ETHER)  
**SHA at audit:** `7c5f87be` plus follow-on skill commits  
**Host at audit:** heartbeat live, last job `p3_25_merge_remainder` ok=true, GPU GTX 1650 4GB idle  
**Version split:** `core/__version__.py` = 0.2.0; `pyproject.toml` = 0.2.1; dashboard 0.7.3  
**Audience:** architects, senior engineers, full team

Companion lists: `docs/AUDIT_SOTA_BACKLOG.md`. Skills updated: goal, keep-pushing, batchphase, pep8-python-reviewer, super-auditor, host-agent-live (hygiene already on origin).

---

## Verdict (do not soften)

ETHER is a **measurement-honest local harness** with a **4B Q4 model**. It is **not** a living autonomous coding agent and it is **not** competitive with Claude Code, Cursor, Codex CLI, or OpenHands as a product.

The infrastructure is more mature than the agent. FINDINGS still stands:

> the infrastructure you built is sound, the measurements it was producing were not, and once they were fixed the pipeline turned out not to beat a bare model.

What changed since FINDINGS: **tool-first on repo-oracle is the only path that beats generate**. Scripted hard pack 5/5. Live hard pack needs a **teacher playbook**. p3_25 merge LIVE scored **1.0 in 31s** with `list_files, bug_comments, replace_once x3, run_tests`. That is Grok's worksheet, not qwen3.5:4b skill. It stays **SEED_DENY** — correctly.

Eligible honest_rate **1.0 / n=80** is greeter+wallet. Raw live honest is ~0.91. Soft launch is blocked. Training wheels stay ON.

**Overall product maturity: 4.4 / 10. Harness honesty: 7 / 10.**

---

## Scores (0–10)

| Subsystem | Score | One-line why |
|-----------|------:|--------------|
| Architecture | 4 | 75kB pipeline god-file, two LLM stacks, 188 ETHER_* flags |
| Tool-first | 6 | Tools exist; 4B needs playbook takeover after 2 observes |
| Measurement honesty | 8 | SEED_DENY, holdout, prompt_guard, retracted +53pp |
| Autonomy / living agent | 3 | FIFO host works; Pipeline has no resume; playbook ≠ self-evolve |
| Planning | 3 | Keyword Selenite; plan JSON not executed as DAG |
| Memory / RAG | 5 | BM25 operational; Citrine needs Qdrant; LoRA TinyCoder |
| Security | 6 | Docker fail-closed; dashboard unauthenticated; no PI defense |
| UX | 5 | Dashboard+WS exist; two CLIs; no TUI; git bus for tutor |
| Live performance | 2 | Live p95 ~590s; 148× vs scripted ledger |
| vs Claude Code | 2 | No tree edit, no LSP, no subagent isolation, 4B ceiling |

---

## Three-audience briefing

### Architects — cascading decisions

1. **Two runtimes.** ToolRuntime (product) vs Pipeline generate vs agent_loop (measured net negative). Default path is ToolRuntime under wheels, but Rose Quartz still defaults `qwen2.5-coder:3b` while multi_llm defaults `qwen3.5:4b`. One silent fallback wasted a day of matrix (`FINDINGS` §12).
2. **Plan is decoration.** `Pipeline.run` always calls Selenite, dumps `ExecutionPlan` JSON into the generate prompt, and never walks `steps[].deps`. Three types named PlanState. Orchestrator Status is discarded (ARCH-006).
3. **God-file + flag entropy.** `core/pipeline.py` ~1655 lines / 75kB. ~188 unique `ETHER_*` identifiers, ~20 documented in `.env.example`. Strangler slices exist; the body is still ACTIVE.
4. **Eligible window vs product claim.** Soft-launch language tracks 0.99. The 1.0 is an allowlist. Architects who ship on that number will launch a greeter bot.
5. **Self-improve is JSON + git, not weights.** LoRA train Unsloth/PEFT raise NotImplementedError. loralib path trains TinyCoder 128→64→32. Dual-window tutor is GitHub, not a socket to 127.0.0.1:8787/ws.

### Senior engineers — highest-leverage code moves

1. **One `select_primary_model()`** used by Rose, multi_llm, measure scripts. Kill 3b silent fallback.
2. **Delete or quarantine `ETHER_AGENT_LOOP` default path.** Trust 0.2 in train_gates is correct; the flag still exists in Pipeline.
3. **Generalize playbook.** p3_25 remainder `replace_once` of the tail block is the template. Next: derive mutations from `bug_comments` AST, not fixture-hardcoded strings.
4. **Cache BM25 index.** `rag_bm25.search` rebuilds 400 files per call (PERF-003).
5. **`git rm --cached` jobs/failed and jobs/done.** `.gitignore` is in; origin still resurrected files until untracked. `scripts/queue_hygiene.py` exists.
6. **Wire `checkpoint.py` into `Pipeline.run`.** Schema on disk, unused.
7. **Stop mutate_doctrine from baking ledger/merge solutions into every system prompt.** Task leakage into the global prompt.

### Full team — what you are looking at

- The Control Matrix at 127.0.0.1:8787 is the operator UI. Completed work is `last_job`, not the failed list.
- Failed jobs that "never go away" were Git restoring tracked JSON on `reset --hard`. That is hygiene, not Ether failing greeter again.
- "Living agent" in docs (infinity gem loop) is **not** what `Pipeline.run` does. Actual loop: rule plan → tools or one-shot generate → sandbox → heuristic critique JSONL → maybe a pytest recovery job.
- A 4B model on 4GB VRAM cannot train LoRA while serving. Dry tick is the honest path.

---

## 20-subsystem diagnostic

### 1. Overall architecture — score 4

**What exists:** Envelope/Registry, 8 gem folders, ToolRuntime, host_agent FIFO, strangler slices, FastAPI dashboard.

**Flaws:** No DI, no event bus, no cancellation token through Pipeline, no streaming on the default LLM path (`stream: False`), checkpoint unwired, gems/__init__.py `__all__ = []` (no ABC). Pipeline is a 75kB sequential script. Thread safety = host FIFO one job. Async = dashboard WS only.

**Fix:** Extract Pipeline.run stages behind LoopRunner (flag already exists, default 0). Freeze new ETHER_* flags (QUAL-005 ratchet 191, already blown).

### 2. Prompt stack — score 4

Five live surfaces, conflicting output contracts (JSON tool vs raw Python). STEP_ORDER prefers edit_lines; mutate_doctrine prefers anchor_edit/replace_once; docs prefer apply_patch. Fixture-specific ledger/merge lines in the **global** system prompt. Apprentice doctrine markdown is never injected. First user turn still says "read tests and broken source" while rules say never re-read.

**Fix:** Single CodingMethod block. Remove fixture spoilers from doctrine. Align first user turn with observe≤2 then mutate.

### 3. Agent loop — score 3

`core/agent_loop.py` is the best-written generate loop in the repo and it **lost** 0.083 vs 0.333 bare+sys. Oracle pass@3 headroom +5.8pp. Verifier saturates on plausible-wrong. ToolRuntime is the product loop. Observe-loop on 4B was p1_248 (6x read_file, 237s). Playbook takeover after 2 observes is now wired in `measure_one`.

**Fix:** Keep agent_loop as a library test of extraction/repair prompts. Product default stays ToolRuntime. Do not BoN.

### 4. Planning — score 3

Selenite: regex fabricate/run + keyword intent. Confidence hardcoded 0.7/0.75. PlanState.should_replan always true under wheels. phase4_swarm_plan ROLE_MAP assigns style→citrine, retrieve→selenite (inverted). spawned: False always.

**Fix:** Execute plan steps as a DAG in ToolRuntime (list/read/mutate/test). Kill swarm JSON theatre or make ROLE_MAP match gems.

### 5. Context engine — score 5

BM25 operational, tests/scripts skipped after leak. Rebuild per search. Symbol index default OFF. context_budget.py meters, Pipeline does not call it. Workspace 3500 chars. Rose num_ctx 32768 vs multi_llm 4096/8192.

**Fix:** Persist BM25 index; enable symbol index on hard fixtures; one ctx policy.

### 6. Tool system — score 6

ToolRuntime specs + phaseG + hard_live (edit_lines, bug_comments, replace_once, anchor_edit, ast_outline). Boot import-order wraps _execute (phaseG after hard). Grandidierite fabricate template raises NotImplementedError. No LSP, no notebook, no browser, no gh, no structured tool-calling API (JSON parsed from text).

**Fix:** Native Ollama tool-calling if 4B supports it; else keep parse_action but log parse_fail as taxonomy. Delete unused pep8_review from the hot path until green.

### 7. File editing — score 5

AST-gated write_file. apply_patch exact match fail-closed. flex_replace stripped-line fallback. p3_23 score 0.5 because anchor_edit on `out.extend(a[i:])` duplicated `if`. p3_25 replace_once of the whole tail → 1.0. No 3-way merge, no workspace undo beyond rollback stack, no language server rename.

**Fix:** Prefer unique-block replace_once. Add apply_patch fuzz only after unique match fails. Keep AST reject.

### 8. Repository intelligence — score 3

symbol_index AST top-level. No call graph, no incremental index, no git blame, no cross-file dataflow. repo_oracle is fixture pytest, not GitHub-scale.

**Fix:** Incremental symbol index on host idle; git status + diff as tools.

### 9. Memory — score 5

experience JSONL gated. failure_graph 300 nodes. memory_bus lessons. Citrine optional Qdrant. vectors.Vector unused. LoRA dry operational; real train stub.

**Fix:** Do not stand up Neo4j. Persist BM25. Keep LoRA dry until pairs+VRAM.

### 10. Reflection — score 4

Labradorite is regex heuristics (line count, eval, for+append). Critique does not rewrite the current Pipeline generate. critique_on_fail enqueues **pytest** jobs. Verifier is real and saturates. Holdout/assert_audit are the crown jewels.

**Fix:** Labradorite LLM-critique only on non-infra FAIL with max_tokens cap; schema root_cause + smallest_experiment already specified — make the gem emit it from traces, not line counts.

### 11. Subagents — score 2

No isolated subagent runtime. phase4_swarm_plan does not spawn. LangGraph optional file checkpoint, not an agent. LangChain adapter wraps ETHER tools, replaces_gems False.

**Fix:** Do not build a swarm. Build **one** ToolRuntime that finishes merge unaided. Then a second worker for tests-only.

### 12. Hooks — score 2

pipeline_hooks is a re-export shim. No plugin entry points. repo_oracle_hook optional post-sandbox. GemRegistry is the plugin system and it is static.

### 13. Provider layer — score 4

Ollama HTTP, retries=0, stream off. Burst grok-3 cap 40/day. Two stacks, two ctx, two default models. No structured output schema. Fast lane max_tokens 1024 (boot floors 1024 for tools).

**Fix:** Unify. Add one retry on empty content. Keep stream off on 4GB (KV).

### 14. UX — score 5

Dashboard 0.7.3, WS /ws 1.5s. Two CLIs. Harness slash cmds. Desktop Windows only. Interrupt = kill process, not mid-pipeline cancel. Unauthenticated promote API.

**Fix:** Bind dashboard to loopback only (already 127.0.0.1). Show last_job as Completed. Filter playbook_* noise (collector still lists 60 done).

### 15. Performance — score 2

Live p50 154s, p95 590s, timeout_rate 0.24. Scripted ~2s. GPU lock correct. Parallelism almost none. BM25 uncached.

**Fix:** Observe-kill + playbook already cut merge from 237s fail to 31s pass. Next: stop calling Ollama when playbook has taken over (p3_25 still listed model qwen3.5 — confirm LLM not paid after takeover).

### 16. Reliability — score 5

Host launcher restart, git origin-wins, zero_click_recovery Windows python.exe hardcoded. Job resurrection via reset — gitignore landed. Pipeline no resume. Silent except pass on amethyst log.

### 17. Security — score 6

Docker fail-closed. Black Tourmaline now zero-violation. prompt_guard is holdout leak, not injection. Retrieved memory re-injected unsanitized (SECURITY.md). Dashboard no auth. shell=True only in harness !cmd.

### 18. Evaluation — score 7

Ablation harness, McNemar, holdout mutation 0.966. Eligible vs raw split is the right honesty. Scoreboard count ≠ pytest count. Playbook vs model not labeled on p3_25 row (measurement gap).

**Fix:** Tag rows `policy=playbook|model`. Never mix into eligible.

### 19. Missing capabilities (vs SOTA coding agents)

LSP, tree-sitter multi-lang, native tool-calling, subagent isolation, plan DAG execution, session fork, cloud rules, PR review, browser, notebooks, secret scanning in CI, streaming tokens to UI, incremental index, unaided hard-file edit on 4B without spoilers.

### 20. Competitive gap

| | ETHER | Claude Code | Cursor | OpenHands | Aider |
|--|------:|------------:|-------:|----------:|------:|
| Architecture | 4 | 9 | 8 | 8 | 6 |
| Planning | 3 | 8 | 7 | 7 | 5 |
| Editing | 5 | 9 | 9 | 8 | 8 |
| Context | 5 | 9 | 9 | 7 | 7 |
| Tooling | 6 | 9 | 8 | 8 | 6 |
| Memory | 5 | 7 | 6 | 6 | 4 |
| Reflection | 4 | 8 | 6 | 6 | 4 |
| Reliability | 5 | 8 | 8 | 7 | 7 |
| Performance | 2 | 8 | 8 | 6 | 7 |
| UX | 5 | 8 | 9 | 6 | 6 |

ETHER wins **honesty of eval** and **local-first 4GB lock**. It loses the product.

---

## Top issues with full fields (P0)

### P0-1 Dual LLM default models
- **Severity:** critical  
- **Impact:** silent 3b vs 4b; days of matrix noise; live timeouts  
- **Likelihood:** certain on any Rose path  
- **Root:** `gems/rose_quartz/router.py` fallback `qwen2.5-coder:3b` vs `multi_llm`/`model_select` 4b  
- **Scenario:** pipeline live uses Rose, host .env 4b ignored  
- **Fix:** one `select_primary_model()`; test pins both  
- **Difficulty:** S  
- **Improvement:** remove a class of false FAILs  
- **Priority:** 1  
- **Time:** 0.5 day

### P0-2 Eligible 1.0 is greeter padding
- **Severity:** critical (product lie if launched)  
- **Impact:** soft-launch on a toy  
- **Likelihood:** high if flags flipped from chat  
- **Root:** SEED_DENY + allowlist  
- **Scenario:** operator sets ETHER_SOFT_LAUNCH=1 after seeing 1.0  
- **Fix:** dashboard labels "eligible=easy"; soft_launch requires unaided merge+ledger  
- **Difficulty:** S  
- **Priority:** 1  
- **Time:** 0.5 day

### P0-3 4B cannot mutate unaided
- **Severity:** high (blocks living-agent claim)  
- **Impact:** hard LIVE timeouts; teacher playbooks  
- **Likelihood:** high (p1_248)  
- **Root:** 4B tool-choice + prompt conflict + no native tools  
- **Scenario:** six read_file then timeout  
- **Fix:** generalize playbook from bug_comments; then fade spoilers  
- **Difficulty:** M  
- **Priority:** 1  
- **Time:** 3–5 days to unaided merge

### P0-4 Pipeline god-file + unwired checkpoint
- **Severity:** high  
- **Impact:** no resume, no cancel, every change is a merge conflict  
- **Fix:** LoopRunner default-on for extracted stages; checkpoint after each stage  
- **Difficulty:** L  
- **Time:** 1–2 weeks

### P0-5 Live latency 148×
- **Severity:** high  
- **Impact:** operator feels "snail speed"  
- **Root:** multi-step LLM on Turing 4GB, not quant  
- **Fix:** playbook/observe-kill already 237s→31s on merge; skip LLM after takeover  
- **Difficulty:** S–M  
- **Time:** 1 day

### P0-6 Prompt fixture spoilers
- **Severity:** high (eval contamination class)  
- **Root:** mutate_doctrine names ledger debit and merge remainder globally  
- **Fix:** inject spoilers only when fixture_root matches  
- **Difficulty:** S  
- **Time:** 0.5 day

### P0-7 Dashboard unauthenticated mutate APIs
- **Severity:** high  
- **Fix:** bind 127.0.0.1 (done) + require token for promote/reconcile  
- **Difficulty:** S  
- **Time:** 0.5 day

---

## 7-phase roadmap (dependency order)

**Phase 1 — Critical (1–2 weeks)**  
Unify model select; fixture-scoped doctrine; tag playbook vs model on scoreboards; queue untrack; skip LLM after takeover; dashboard last_job = completed; token on promote.

**Phase 2 — Architecture (2–4 weeks)**  
LoopRunner default; checkpoint wired; freeze ETHER_* ; extract 200-line slices from pipeline.py until <400 lines; one PlanState type.

**Phase 3 — Performance (1–2 weeks, overlaps 1)**  
BM25 cache; ctx policy; live step timeout 45s already — enforce observe-kill so wall never 590s; FAST-first governor stays.

**Phase 4 — Reasoning (2–3 weeks)**  
Execute Selenite steps as ToolRuntime plan; Labradorite from traces not line-count; no BoN.

**Phase 5 — Autonomy (3–4 weeks)**  
Unaided merge+ledger LIVE x3; then consider wheels language — still human flag. Wire critique→pending without pytest-only jobs.

**Phase 6 — Advanced (4+ weeks)**  
Git+symbol tools; MCP stdio client actually implemented; single extra-language AST; not Neo4j.

**Phase 7 — Experimental**  
Real LoRA on cousin hardware; native tool-calling; isolated test-worker; never vLLM on 1650.

---

## Living-agent gap (user essential ask)

Self-learn / self-evolve **today**: lessons JSONL, experience vault, failure_graph, preference pairs, playbook takeover, dual-window git.

Self-learn / self-evolve **not today**: weight updates, unaided hard-file skill, plan DAG, subagents, Qdrant memory as default, websocket tutor.

The transformation required is **not** more databases. It is: 4B emits replace_once from bug_comments without a fixture dictionary, and Pipeline can resume after crash. Until then, calling ETHER a living autonomous agent is marketing, and this audit refuses it.
