"""Append FINDINGS §13 Phase E if missing."""
from pathlib import Path

SECTION = """
---

## 13. Phase E — mutation restore (2026-08-01)

Host `qwen3.5:4b`. Six named mutations applied to `_fixed_solutions`, oracle = project pytest.

| arm | pass/6 |
|-----|--------|
| direct scripted | 6/6 |
| direct live | **3/6** |
| bare live | **1/6** |

Direct live PASS: `lru_no_evict`, `merge_drop_b_tail`, `intervals_no_sort`.  
Direct live FAIL (max_steps): both ledger mutations, `topo_drop_cycle_raise` (score 0.571).  
Bare live PASS only: `topo_drop_cycle_raise`.

### Implications

1. Phase D 5/5 does **not** automatically transfer to regression-style mutations — ledger/topo need more budget or stronger tool prompts.
2. Tools still outperform bare on this pack (3/6 vs 1/6); bare is not competitive on lru/merge/intervals.
3. Next evidence-ranked step remains **real external repos** (TASKS #1), not selector polish.
"""

p = Path("docs/FINDINGS.md")
t = p.read_text(encoding="utf-8")
if "## 13. Phase E" in t:
    print("FINDINGS §13 already present")
else:
    p.write_text(t.rstrip() + "\n" + SECTION, encoding="utf-8")
    print("FINDINGS §13 appended")
print("done")
