import json, os, sys
from pathlib import Path
root = Path(sys.argv[1]).resolve(); sys.path.insert(0, str(root)); os.chdir(root)
from core.agent import goal_source as gs
from core.agent.goal_quality import check
from core.learning import arm_behaviour, STRATEGIES
from core.kernel.context_budget import context_char_budget
goals = list(json.load(open("config/goal_seed.json"))["goals"].values())
out = {}
for ctx in ("2048", "4096", "8192"):
    os.environ["ETHER_MODEL_CTX"] = ctx
    over = spoiled = n = 0; mx = 0
    for g in goals:
        for arm in STRATEGIES:
            p = gs.build_prompt(root, g, arm_behaviour(arm)); n += 1; mx = max(mx, len(p))
            over += len(p) > context_char_budget()
            cur = (root / g["file"]).read_text(encoding="utf-8", errors="ignore")
            spoiled += not check(g, p, cur)["ok"]
    out[ctx] = {"prompts": n, "over_budget": over, "rejected_by_guard": spoiled, "max_chars": mx, "budget": context_char_budget()}
print(json.dumps(out, indent=1))
