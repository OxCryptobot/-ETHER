"""Coding method schema — mentor doctrine in machine form for GEMS / ToolRuntime.

Agents import SYSTEM_RULES or CodingMethod.as_prompt_block() instead of
inventing process each run.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Sequence, Tuple

# Preferred step order for tool-first agents
STEP_ORDER: Tuple[str, ...] = (
    "list_files",
    "bug_comments",
    "read_file",  # tests first, then source (numbered)
    "grep",
    "glob",
    "edit_lines",  # preferred for 4B live — line span from numbered read
    "apply_patch",  # preferred over write_file for edits
    "write_file",
    "run_tests",
    "pep8_review",
    "rollback",
    "done",
)

SYSTEM_RULES: Tuple[str, ...] = (
    "Output ONE JSON tool call per turn: {\"tool\": name, \"args\": {...}}.",
    "Read failing tests before editing source.",
    "Call bug_comments once to surface author-marked defects.",
    "read_file returns numbered lines; use edit_lines(start_line,end_line,new).",
    "Prefer edit_lines or apply_patch; write_file only for new/full files.",
    "After two observe tools, mutate. Never re-read the same file.",
    "After every meaningful edit, run_tests.",
    "If run_tests fails 3 times without score gain, done with reason no_progress.",
    "Never emit eval/exec/__import__ dynamic code.",
    "Python must AST-parse; never write syntax-broken code.",
    "pep8_review after tests pass; style does not override failing tests.",
    "One hypothesis per cycle; smallest change that could green the tests.",
    "done only when tests pass or honest give-up with typed reason.",
)


@dataclass
class CodingMethod:
    """Structured coding contract for an agent run."""

    name: str = "ether_tool_first_v1"
    step_order: Sequence[str] = field(default_factory=lambda: STEP_ORDER)
    rules: Sequence[str] = field(default_factory=lambda: SYSTEM_RULES)
    max_stagnant_test_fails: int = 3
    prefer_patch: bool = True
    require_read_before_write: bool = True
    style_after_green: bool = True

    def as_prompt_block(self) -> str:
        rules = "\n".join(f"- {r}" for r in self.rules)
        order = ", ".join(self.step_order)
        return (
            f"Coding method: {self.name}\n"
            f"Preferred tool order: {order}\n"
            f"Rules:\n{rules}\n"
        )

    def checklist(self) -> List[str]:
        return [
            "read tests",
            "read source",
            "one hypothesis",
            "surgical edit",
            "run_tests",
            "pep8_review if green",
            "done",
        ]


def default_method() -> CodingMethod:
    return CodingMethod()


def prompt_suffix() -> str:
    """Short block to append to ToolRuntime system prompts."""
    return default_method().as_prompt_block()
