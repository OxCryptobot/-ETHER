"""Apply nested-JSON parse + failed-test surface + _retry.

Requires scripts/_parse_snippet.py and scripts/_obs_snippet.py on disk
(shipped in same commit). Run: python scripts/apply_parse_fix.py
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PARSE = (ROOT / "_parse_snippet.py").read_text(encoding="utf-8")
OBS = (ROOT / "_obs_snippet.py").read_text(encoding="utf-8")

p = Path("core/tool_runtime.py")
t = p.read_text(encoding="utf-8")

if "_extract_json_objects" not in t:
    start = t.find("def parse_action(text: str)")
    end = t.find("\ndef _blocked")
    if start < 0 or end < 0:
        raise SystemExit("parse markers missing")
    t = t[:start] + PARSE + t[end:]
    print("parse: applied")
else:
    print("parse: already present")

if '"failed"' not in t and "'failed'" not in t:
    start = t.find("    def _obs_tests")
    end = t.find("\n    def _execute")
    if start < 0 or end < 0:
        print("WARN: obs markers missing")
    else:
        t = t[:start] + OBS + t[end:]
        print("obs_tests: applied")
else:
    print("obs_tests: already present")

if 'tool == "_retry"' not in t:
    needle = (
        '        if tool == "done":\n'
        '            return {"ok": True, "reason": str(args.get("reason") or "done")}\n'
        '        return {"ok": False, "error": f"unknown tool: {tool}"}'
    )
    repl = (
        '        if tool == "done":\n'
        '            return {"ok": True, "reason": str(args.get("reason") or "done")}\n'
        '        if tool == "_retry":\n'
        '            return {\n'
        '                "ok": False,\n'
        '                "error": "unparseable",\n'
        '                "hint": "Reply with ONE JSON object only",\n'
        '            }\n'
        '        return {"ok": False, "error": f"unknown tool: {tool}"}'
    )
    if needle not in t:
        print("WARN: execute needle missing")
    else:
        t = t.replace(needle, repl, 1)
        print("execute: _retry wired")
else:
    print("execute: already has _retry")

ast.parse(t)
p.write_text(t, encoding="utf-8")
print("done", len(t))
