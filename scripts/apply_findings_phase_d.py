"""Append FINDINGS §12 Phase D if missing."""
from pathlib import Path

SECTION = '''
---

## 12. Phase D — tool path on hard repo-oracle pack (2026-08-01)

### Setup

- Host: GTX 1650 4GB / 12GB, `ETHER_PRIMARY_MODEL=qwen3.5:4b`
- Pack: lru, merge, ledger, topo, intervals (project pytest oracle)
- Arms: **direct** (ToolRuntime), **pipeline** (Pipeline + tools + same-workspace verify), **bare** (Pipeline tools off)
- Runner: `scripts/batch_phase_d.py` (must `load_dotenv`; must pass `--max-steps`)

### Result

| arm | pass/5 |
|-----|--------|
| direct | 5/5 |
| pipeline (max_steps=16) | 5/5 |
| bare | 0/5 |

Pipeline under wrong config looked worse: with Rose default `qwen2.5-coder:3b` and 12 steps, pipeline was **3/5** (ledger/topo `max_steps`). Same fixtures **5/5** once model and step budget matched host intent.

### What this does and does not overturn

- Does **not** overturn §1 holdout generate ablation (ether ≤ bare+sys).
- Does show the **repo-grounded** direction from §8/§11 is real: tools + project tests beat one-shot generate on this pack.
- Best-of-N agent loop (§11) stays off — different mechanism, already net negative on holdout.

### Product implications

1. Default product path for fix-tasks: tool runtime ON, Clear Quartz re-verify on the tool workspace (not generate-first).
2. Always print/resolve `ETHER_PRIMARY_MODEL` in measure scripts; silent 3b fallback wasted a day of matrix noise.
3. Keep curriculum / bandit / flywheel off until a measurement on this task class says otherwise.
'''

p = Path("docs/FINDINGS.md")
t = p.read_text(encoding="utf-8")
if "## 12. Phase D" in t:
    print("FINDINGS §12 already present")
else:
    p.write_text(t.rstrip() + "\n" + SECTION, encoding="utf-8")
    print("FINDINGS §12 appended")
print("done")
