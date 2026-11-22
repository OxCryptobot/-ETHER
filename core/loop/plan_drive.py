"""Map fix-plan actions to ToolRuntime tool names. Planner drives the loop."""
from __future__ import annotations

from typing import Dict, List

from core.loop.fix_dag import fix_plan, walk_fix

ACTION_TO_TOOLS: Dict[str, List[str]] = {
    "observe": ["list_files", "git_status", "read_file"],
    "mutate": ["bug_comments", "replace_once", "apply_patch"],
    "test": ["run_tests"],
    "validate": ["pep8_review", "done"],
}


def tools_for_plan(objective: str = "fix") -> List[str]:
    plan = fix_plan(objective)
    out: List[str] = []
    for step in plan.steps:
        out.extend(ACTION_TO_TOOLS.get(step.action, []))
    return out


def planner_drives(objective: str = "fix") -> bool:
    tools = tools_for_plan(objective)
    walked = walk_fix(objective)
    return "run_tests" in tools and len(walked) >= 3
