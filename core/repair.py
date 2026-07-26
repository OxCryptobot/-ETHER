"""Repair library — taxonomy + failure-graph templates (skilled retries)."""

from __future__ import annotations

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
        "Fix ALL syntax/indentation errors. Valid Python only. No markdown fences."
    ),
    "NameError": (
        "A name is undefined. Define every symbol before use; stdlib only."
    ),
    "ImportError": (
        "Remove non-stdlib imports. Bare Docker Python has no third-party packages."
    ),
    "AssertionError": (
        "Logic failed asserts. Fix the algorithm; keep the asserts."
    ),
    "TypeError": (
        "Wrong types or arity. Match the objective signatures exactly."
    ),
    "ValueError": (
        "Invalid values. Handle edge cases (empty, zero, None)."
    ),
    "Timeout": (
        "Too slow or infinite loop. Use bounded O(n)/O(n log n) logic."
    ),
    "runtime": (
        "Runtime failure. Smallest correct fix; include asserts."
    ),
}


def repair_prompt(objective: str, code: str, stderr: str, strategy_hint: str = "") -> str:
    info = classify_stderr(stderr)
    kind = info["kind"]
    advice = _TEMPLATES.get(kind, _TEMPLATES["runtime"])
    try:
        from core.failure_graph import repair_hint, observe

        observe(stderr, repaired_ok=False)
        graph_hint = repair_hint(stderr)
        if graph_hint:
            advice = f"{advice}\nGraph template: {graph_hint}"
    except Exception:
        pass

    cleaned = code or ""
    if cleaned.strip().startswith("```"):
        lines = cleaned.split("\n")[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines)

    # fail-kind biased experience
    exp_block = ""
    try:
        from core.experience import retrieve

        exp_block = retrieve(objective, k=2, fail_kind=kind).get("block") or ""
    except Exception:
        pass

    prompt = (
        f"Repair this failed Python solution.\n"
        f"Failure class: {kind}\n"
        f"Repair directive: {advice}\n"
        f"Strategy: {strategy_hint or 'defensive; include asserts'}\n\n"
        f"Objective:\n{objective}\n\n"
        f"Previous code:\n{cleaned}\n\n"
        f"Stderr/stdout:\n{(stderr or '')[:1200]}\n\n"
    )
    if exp_block:
        prompt += f"Related experience:\n{exp_block}\n\n"
    prompt += "Return only complete executable Python code. No markdown."
    return prompt
