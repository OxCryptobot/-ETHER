"""Apply ledger loop nudges to tool_runtime. Run: python scripts/apply_ledger_nudge.py"""
from __future__ import annotations
import ast
from pathlib import Path

p = Path("core/tool_runtime.py")
t = p.read_text(encoding="utf-8")
changed = False

old_begin = '{"role": "user", "content": "Begin. Call a tool."}'
new_begin = (
    '{"role": "user", "content": "Begin. First list_files, then read_file '
    'the tests and the broken source, then fix and run_tests."}'
)
if old_begin in t:
    t = t.replace(old_begin, new_begin, 1)
    print("begin: updated")
    changed = True
elif "First list_files" in t:
    print("begin: already")
else:
    print("WARN: begin not found")

if "still_failing" not in t:
    pos = t.find('reason="tests passed"')
    if pos < 0:
        print("WARN: tests passed marker missing")
    else:
        done_pos = t.find('\n                if tool == "done":', pos)
        if done_pos < 0:
            print("WARN: done anchor missing")
        else:
            insert = (
                '\n                    fails = obs.get("failed") or []\n'
                '                    if fails:\n'
                '                        obs = dict(obs)\n'
                '                        obs["still_failing"] = fails[:8]\n'
                '                        obs["hint"] = "Fix ALL remaining failures. Re-read source if needed."\n'
            )
            t = t[:done_pos] + insert + t[done_pos:]
            print("still_failing: added")
            changed = True
else:
    print("still_failing: already")

if changed:
    ast.parse(t)
    p.write_text(t, encoding="utf-8")
    print("done", len(t))
else:
    print("no changes")
