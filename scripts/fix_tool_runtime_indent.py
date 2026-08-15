"""Emergency fix: _system_prompt was nested inside _execute with bad indent.

Symptom: IndentationError line 311/312 → tool_runtime_fallback always.
Idempotent. Run: python -m scripts.fix_tool_runtime_indent
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "core" / "tool_runtime.py"

BROKEN_NEST = "        def _system_prompt(self, objective: str) -> str:"
FIXED_DEF = "    def _system_prompt(self, objective: str) -> str:"

BODY = '''    def _system_prompt(self, objective: str) -> str:
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
    # Already good?
    try:
        compile(text, str(TARGET), "exec")
        if BROKEN_NEST not in text and "from core.coding_method import prompt_suffix" in text:
            print("already_ok")
            return 0
    except SyntaxError as e:
        print("syntax_before", e)

    if BROKEN_NEST not in text:
        # Missing method entirely — insert before _snapshot_code
        marker = "    def _snapshot_code(self) -> Dict[str, str]:"
        if marker not in text:
            print("no_snapshot_anchor")
            return 2
        body = BODY.replace("\\\\n", "\\n")
        text = text.replace(marker, body + "\n" + marker, 1)
    else:
        # Remove nested broken block through the broken return, keep _snapshot_code
        start = text.index(BROKEN_NEST)
        snap = "    def _snapshot_code(self) -> Dict[str, str]:"
        end = text.index(snap, start)
        body = BODY.replace("\\\\n", "\\n")
        text = text[:start] + body + "\n" + text[end:]

    compile(text, str(TARGET), "exec")
    TARGET.write_text(text, encoding="utf-8")
    print("fixed", TARGET)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
