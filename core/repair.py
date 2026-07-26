"""Classify sandbox failures for structured repair prompts."""

from __future__ import annotations

import re
from typing import Dict


def classify_stderr(stderr: str) -> Dict[str, str]:
    text = stderr or ""
    kind = "runtime"
    if "SyntaxError" in text or "IndentationError" in text:
        kind = "syntax"
    elif "NameError" in text:
        kind = "name"
    elif "ImportError" in text or "ModuleNotFoundError" in text:
        kind = "import"
    elif "AssertionError" in text:
        kind = "assert"
    elif "TypeError" in text:
        kind = "type"
    elif "Timeout" in text or "timeout" in text.lower():
        kind = "timeout"

    hints = {
        "syntax": "Fix syntax/indentation. Ensure valid Python only.",
        "name": "Define every name before use; check typos.",
        "import": "Remove unavailable imports; use stdlib only.",
        "assert": "Make asserts match actual behavior or fix logic.",
        "type": "Fix argument types and None handling.",
        "timeout": "Simplify loops; avoid infinite iteration.",
        "runtime": "Fix the exception; keep code complete and executable.",
    }
    return {"kind": kind, "hint": hints[kind], "excerpt": text[:800]}


def repair_prompt(objective: str, code: str, stderr: str, strategy_hint: str) -> str:
    info = classify_stderr(stderr)
    return (
        f"Previous code failed in sandbox.\n"
        f"Failure class: {info['kind']}\n"
        f"Repair hint: {info['hint']}\n"
        f"Objective: {objective}\n\n"
        f"Broken code:\n{code}\n\n"
        f"Stderr:\n{info['excerpt']}\n\n"
        f"Strategy: {strategy_hint}\n"
        "Write fixed, complete, executable Python only. No markdown."
    )
