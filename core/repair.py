"""Repair library — stderr taxonomy → fixed templates (RL-lite)."""

from __future__ import annotations

import re
from typing import Dict


def classify_stderr(stderr: str) -> Dict[str, str]:
    s = stderr or ""
    kind = "runtime"
    if "SyntaxError" in s or "IndentationError" in s:
        kind = "SyntaxError"
    elif "NameError" in s:
        kind = "NameError"
    elif "ImportError" in s or "ModuleNotFoundError" in s:
        kind = "ImportError"
    elif "AssertionError" in s:
        kind = "AssertionError"
    elif "TypeError" in s:
        kind = "TypeError"
    elif "ValueError" in s:
        kind = "ValueError"
    elif "Timeout" in s or "timed out" in s.lower():
        kind = "Timeout"
    return {"kind": kind, "brief": s[:240]}


_TEMPLATES = {
    "SyntaxError": (
        "Fix ALL syntax/indentation errors. Return complete executable Python only. "
        "No markdown fences. Prefer simple statements."
    ),
    "NameError": (
        "A name is undefined. Define every name before use or import the stdlib symbol. "
        "Do not invent third-party packages."
    ),
    "ImportError": (
        "Remove non-stdlib imports. Use only Python standard library available in a bare container."
    ),
    "AssertionError": (
        "Logic failed an assert. Fix the algorithm to satisfy the stated behavior; keep asserts."
    ),
    "TypeError": (
        "Wrong types or arity. Match parameter types to the objective; coerce carefully."
    ),
    "ValueError": (
        "Invalid values. Add guards or correct the computation for edge cases."
    ),
    "Timeout": (
        "Code was too slow or hung. Use an O(n) or better approach; avoid infinite loops."
    ),
    "runtime": (
        "Runtime failure. Fix the crash; keep the solution minimal and include asserts."
    ),
}


def repair_prompt(objective: str, code: str, stderr: str, strategy_hint: str = "") -> str:
    info = classify_stderr(stderr)
    kind = info["kind"]
    advice = _TEMPLATES.get(kind, _TEMPLATES["runtime"])
    # strip accidental fences in prior code for clarity
    cleaned = code or ""
    if cleaned.strip().startswith("```"):
        lines = cleaned.split("\n")[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines)
    return (
        f"Repair this failed Python solution.\n"
        f"Failure class: {kind}\n"
        f"Repair directive: {advice}\n"
        f"Strategy: {strategy_hint or 'be defensive; include asserts'}\n\n"
        f"Objective:\n{objective}\n\n"
        f"Previous code:\n{cleaned}\n\n"
        f"Stderr/stdout:\n{(stderr or '')[:1200]}\n\n"
        f"Return only complete executable Python code. No markdown."
    )
