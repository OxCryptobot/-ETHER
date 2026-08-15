"""Inject coding_method.prompt_suffix into ToolRuntime._system_prompt.

Idempotent. Run: python -m scripts.patch_doctrine_prompt
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "core" / "tool_runtime.py"


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    if "from core.coding_method import prompt_suffix" in text:
        print("already_patched")
        return 0

    marker = "def _system_prompt(self, objective: str) -> str:"
    if marker not in text:
        print("anchor_missing")
        return 2

    new_fn = '''    def _system_prompt(self, objective: str) -> str:
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
    # Fix double-escaped newlines to real Python source escapes
    new_fn = new_fn.replace("\\\\n", "\\n")

    start = text.index(marker)
    # Find end of function: next method at same indent
    rest = text[start:]
    lines = rest.splitlines(keepends=True)
    end_rel = len(lines[0])
    for line in lines[1:]:
        if line.startswith("    def ") or line.startswith("def "):
            break
        end_rel += len(line)
    else:
        print("end_missing")
        return 3

    updated = text[:start] + new_fn + "\n" + text[start + end_rel :]
    TARGET.write_text(updated, encoding="utf-8")
    print("patched", TARGET)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
