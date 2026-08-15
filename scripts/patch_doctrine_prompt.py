"""Inject coding_method.prompt_suffix into ToolRuntime._system_prompt.

Idempotent. Run: python -m scripts.patch_doctrine_prompt
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "core" / "tool_runtime.py"

OLD = '''    def _system_prompt(self, objective: str) -> str:
        tools = "\\n".join(f"- {t['name']}: {t['doc']}" for t in TOOL_SPECS)
        return (
            "You are a coding agent with tools. Each turn, output ONE JSON object only:\\n"
            '  {"tool": "<name>", "args": {...}}\\n'
            "No markdown, no prose. Tools:\\n"
            f"{tools}\\n\\n"
            f"Objective:\\n{objective}\\n"
            "Strategy: list/read to understand, write_file to fix, run_tests to verify, "
            "done when tests pass."
        )
'''

NEW = '''    def _system_prompt(self, objective: str) -> str:
        tools = "\\n".join(f"- {t['name']}: {t['doc']}" for t in TOOL_SPECS)
        try:
            from core.coding_method import prompt_suffix
            doctrine = prompt_suffix()
        except Exception:
            doctrine = (
                "Rules: read tests first; surgical edits; run_tests after edits; "
                "stop on no_progress after 3 stagnant fails.\\n"
            )
        return (
            "You are a coding agent with tools. Each turn, output ONE JSON object only:\\n"
            '  {"tool": "<name>", "args": {...}}\\n'
            "No markdown, no prose. Tools:\\n"
            f"{tools}\\n\\n"
            f"{doctrine}\\n"
            f"Objective:\\n{objective}\\n"
            "Strategy: list/read tests+source, apply_patch or write_file, run_tests, "
            "pep8_review when green, done when tests pass."
        )
'''


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    if "from core.coding_method import prompt_suffix" in text:
        print("already_patched")
        return 0
    if OLD not in text:
        print("anchor_missing")
        return 2
    TARGET.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
    print("patched", TARGET)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
