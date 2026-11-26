"""Remove local ClearQuartzRequest import that shadows module-level import.

Python treats a function-scope `from ... import ClearQuartzRequest` as making
the name local for the *entire* function. Paths that skip that branch then
hit UnboundLocalError at the main sandbox Envelope.
"""
from pathlib import Path
import ast, re

p = Path("core/pipeline.py")
t = p.read_text(encoding="utf-8")
n = 0
for pat in (
    "                        from core.schemas import ClearQuartzRequest, ClearQuartzResponse\n",
    "                from core.schemas import ClearQuartzRequest, ClearQuartzResponse\n",
    "                    from core.schemas import ClearQuartzRequest, ClearQuartzResponse\n",
):
    while pat in t:
        t = t.replace(pat, "", 1)
        n += 1
t2, n2 = re.subn(
    r"^[ \t]+from core\.schemas import ClearQuartzRequest, ClearQuartzResponse\n",
    "",
    t,
    flags=re.M,
)
t = t2
n += n2
ast.parse(t)
p.write_text(t, encoding="utf-8")
print(f"removed {n} local ClearQuartz imports")
print("done", len(t))
