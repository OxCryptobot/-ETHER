"""Apply nested-JSON parse fix + _retry instead of done-on-unparseable.

Root cause: parse_action used {[^{}]+} which cannot parse write_file content
containing braces. That forced tool=done (unparseable) and killed ledger runs.

Run:  .\\.venv\\Scripts\\python.exe scripts\\apply_parse_fix.py
"""
from __future__ import annotations

import ast
from pathlib import Path

p = Path("core/tool_runtime.py")
t = p.read_text(encoding="utf-8")
if "_extract_json_objects" in t and 'tool == "_retry"' in t:
    print("already applied")
    raise SystemExit(0)

start = t.find("def parse_action(text: str)")
end = t.find("\ndef _blocked")
if start < 0 or end < 0:
    raise SystemExit("markers not found")

new_parse = r'''def _extract_json_objects(raw: str) -> List[str]:
    """Pull candidate JSON objects, including nested braces (write_file content)."""
    out: List[str] = []
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fence:
        out.append(fence.group(1))
    i = 0
    while i < len(raw):
        if raw[i] != "{":
            i += 1
            continue
        depth = 0
        in_str = False
        esc = False
        j = i
        while j < len(raw):
            ch = raw[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        out.append(raw[i : j + 1])
                        break
            j += 1
        i = j + 1 if depth == 0 else i + 1
    return out


def parse_action(text: str) -> Dict[str, Any]:
    """Extract a single tool call. Nested {} in write content is supported.

    Unparseable returns tool=_retry (loop continues) instead of done.
    """
    raw = (text or "").strip()
    if not raw:
        return {"tool": "_retry", "args": {"reason": "empty model output"}}
    for c in _extract_json_objects(raw):
        if '"tool"' not in c and "'tool'" not in c:
            continue
        try:
            obj = json.loads(c)
        except json.JSONDecodeError:
            try:
                obj, _ = json.JSONDecoder().raw_decode(c)
            except json.JSONDecodeError:
                continue
        if isinstance(obj, dict) and obj.get("tool"):
            tool = str(obj["tool"]).strip()
            if tool.startswith("_"):
                continue
            args = obj.get("args") if isinstance(obj.get("args"), dict) else {}
            return {"tool": tool, "args": args}
    return {"tool": "_retry", "args": {"reason": "unparseable action"}}


'''

t = t[:start] + new_parse + t[end:]

old_done = '''        if tool == "done":
            return {"ok": True, "reason": str(args.get("reason") or "done")}
        return {"ok": False, "error": f"unknown tool: {tool}"}'''
new_done = '''        if tool == "done":
            return {"ok": True, "reason": str(args.get("reason") or "done")}
        if tool == "_retry":
            return {
                "ok": False,
                "error": "unparseable",
                "hint": 'Reply with ONE JSON object only: {"tool":"...","args":{...}}',
            }
        return {"ok": False, "error": f"unknown tool: {tool}"}'''
if old_done not in t:
    raise SystemExit("_execute done block not found")
t = t.replace(old_done, new_done, 1)

old_obs = '''                messages.append(
                    {
                        "role": "user",
                        "content": "Observation:\\n"
                        + json.dumps(rec.observation, default=str)[:2000]
                        + "\\nNext tool call (JSON only).",
                    }
                )'''
# Fix the above - use actual newlines in source as in file
old_obs = (
    "                messages.append(\n"
    "                    {\n"
    '                        "role": "user",\n'
    '                        "content": "Observation:\\n"\n'
    "                        + json.dumps(rec.observation, default=str)[:2000]\n"
    '                        + "\\nNext tool call (JSON only).",\n'
    "                    }\n"
    "                )"
)

# Simpler: line-based replace for observation footer
if '"\\nNext tool call (JSON only)."' in t or '"\nNext tool call (JSON only)."' in t:
    t2 = t.replace(
        '+ "\nNext tool call (JSON only).",
                    }
                )',
        '''+ (
                            "\nFORMAT: output exactly one JSON object, no prose."
                            if (tool == "_retry" or not rec.ok)
                            else ""
                        )
                        + "\nNext tool call (JSON only).",
                    }
                )''',
        1,
    )
    if t2 != t:
        t = t2
        print("obs nudge patched")

old_sys = (
    '            "Strategy: list/read to understand, write_file to fix, run_tests to verify, "\n'
    '            "done when tests pass."'
)
new_sys = (
    '            "Strategy: list/read tests AND source, write_file to fix, run_tests to verify, "\n'
    '            "done only when tests pass. If tests mention raises/ValueError/cycle, implement that. "\n'
    '            "Multi-file: fix every broken module. ALWAYS reply with pure JSON tool call."'
)
if old_sys in t:
    t = t.replace(old_sys, new_sys, 1)
    print("sys patched")

ast.parse(t)
p.write_text(t, encoding="utf-8")
print("applied", len(t))
