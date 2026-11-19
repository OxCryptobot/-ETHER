"""Build config/goal_seed.json from a pytest junit xml (reviewed seed for a fresh host).

    python -m pytest tests -q --continue-on-collection-errors --tb=short --junitxml=out/t.xml
    python -m scripts.goal_seed out/t.xml
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path


def build(root: Path, xml: Path) -> dict:
    from core.agent import goal_source as gs

    goals, dropped = {}, {}
    tree = ET.parse(xml).getroot()
    for tc in tree.iter("testcase"):
        for tag in ("failure", "error"):
            el = tc.find(tag)
            if el is None:
                continue
            nid = gs.nodeid_of(root, tc.get("classname") or "", tc.get("name") or "")
            text = ((el.get("message") or "") + "\n" + (el.text or ""))[-2000:]
            goal = gs.goal_from_failure(root, nid, text)
            if goal is None:
                dropped[nid] = "infra_or_untargetable"
                continue
            goal["tractability"] = gs.tractability(root, goal)
            goals[goal["id"]] = goal
    for goal in gs.lint_goals(root):
        goal["tractability"] = gs.tractability(root, goal)
        goals.setdefault(goal["id"], goal)
    return {"goals": goals, "done": [], "dropped": dropped, "cursor": 0, "source": str(xml.name),
            "kinds": dict(Counter(g["kind"] for g in goals.values()))}


def main(argv: list) -> int:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    data = build(root, Path(argv[0]))
    out = root / "config" / "goal_seed.json"
    out.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"goals": len(data["goals"]), "dropped": len(data["dropped"]), "kinds": data["kinds"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
