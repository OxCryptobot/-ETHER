"""Apply nested-JSON parse fix. Run: python scripts/apply_parse_fix.py"""
from __future__ import annotations
import ast, base64
from pathlib import Path

SECTION = base64.b64decode(
    "ZGVmIF9leHRyYWN0X2pzb25fb2JqZWN0cyhyYXc6IHN0cikgLT4gTGlzdFtzdHJdOgogICAg"
    "b3V0OiBMaXN0W3N0cl0gPSBbXQogICAgZmVuY2UgPSByZS5zZWFyY2gociJcYGBgKD86anNv"
    "bik/XFxzKihcXHsuKj9cXH0pXFxzKlxgYGAiLCByYXcsIHJlLkRPVEFMTCkKICAgIGlmIGZl"
    "bmNlOgogICAgICAgIG91dC5hcHBlbmQoZmVuY2UuZ3JvdXAoMSkpCiAgICBpID0gMAogICAg"
    "d2hpbGUgaSA8IGxlbihyYXcpOgogICAgICAgIGlmIHJhd1tpXSAhPSAieyI6CiAgICAgICAg"
    "ICAgIGkgKz0gMQogICAgICAgICAgICBjb250aW51ZQogICAgICAgIGRlcHRoID0gMAogICAg"
    "ICAgIGluX3N0ciA9IEZhbHNlCiAgICAgICAgZXNjID0gRmFsc2UKICAgICAgICBqID0gaQog"
    "ICAgICAgIHdoaWxlIGogPCBsZW4ocmF3KToKICAgICAgICAgICAgY2ggPSByYXdbal0KICAg"
    "ICAgICAgICAgaWYgaW5fc3RyOgogICAgICAgICAgICAgICAgaWYgZXNjOgogICAgICAgICAg"
    "ICAgICAgICAgIGVzYyA9IEZhbHNlCiAgICAgICAgICAgICAgICBlbGlmIGNoID09IFwiXFxc"
    "XCI6CiAgICAgICAgICAgICAgICAgICAgZXNjID0gVHJ1ZQogICAgICAgICAgICAgICAgZWxp"
    "ZiBjaCA9PSAnXCI6CiAgICAgICAgICAgICAgICAgICAgaW5fc3RyID0gRmFsc2UKICAgICAg"
    "ICAgICAgZWxzZToKICAgICAgICAgICAgICAgIGlmIGNoID09ICdcIic6CiAgICAgICAgICAg"
    "ICAgICAgICAgaW5fc3RyID0gVHJ1ZQogICAgICAgICAgICAgICAgZWxpZiBjaCA9PSAieyI6"
    "CiAgICAgICAgICAgICAgICAgICAgZGVwdGggKz0gMQogICAgICAgICAgICAgICAgZWxpZiBj"
    "aCA9PSAifSI6CiAgICAgICAgICAgICAgICAgICAgZGVwdGggLT0gMQogICAgICAgICAgICAg"
    "ICAgICAgIGlmIGRlcHRoID09IDA6CiAgICAgICAgICAgICAgICAgICAgICAgIG91dC5hcHBl"
    "bmQocmF3W2kgOiBqICsgMV0pCiAgICAgICAgICAgICAgICAgICAgICAgIGJyZWFrCiAgICAg"
    "ICAgICAgIGogKz0gMQogICAgICAgIGkgPSBqICsgMSBpZiBkZXB0aCA9PSAwIGVsc2UgaSAr"
    "IDEKICAgIHJldHVybiBvdXQKXG5cbmRlZiBwYXJzZV9hY3Rpb24odGV4dDogc3RyKSAtPiBE"
    "aWN0W3N0ciwgQW55XTpcbiAgICByYXcgPSAodGV4dCBvciBcIlwiKS5zdHJpcCgpXG4gICAg"
    "aWYgbm90IHJhdzpcbiAgICAgICAgcmV0dXJuIHtcInRvb2xcIjogXCJfcmV0cnlcIiwgXCJh"
    "cmdzXCI6IHtcInJlYXNvblwiOiBcImVtcHR5IG1vZGVsIG91dHB1dFwifX1cbiAgICBmb3Ig"
    "YyBpbiBfZXh0cmFjdF9qc29uX29iamVjdHMocmF3KTpcbiAgICAgICAgaWYgJ1widG9vbFwi"
    "JyBub3QgaW4gYyBhbmQgXCIndG9vbCdcIiBub3QgaW4gYzpcbiAgICAgICAgICAgIGNvbnRp"
    "bnVlXG4gICAgICAgIHRyeTpcbiAgICAgICAgICAgIG9iaiA9IGpzb24ubG9hZHMoYylcbiAg"
    "ICAgICAgZXhjZXB0IGpzb24uSlNPTkRlY29kZUVycm9yOlxuICAgICAgICAgICAgdHJ5Olxu"
    "ICAgICAgICAgICAgICAgIG9iaiwgXyA9IGpzb24uSlNPTkRlY29kZXIoKS5yYXdfZGVjb2Rl"
    "KGMpXG4gICAgICAgICAgICBleGNlcHQganNvbi5KU09ORGVjb2RlRXJyb3I6XG4gICAgICAg"
    "ICAgICAgICAgY29udGludWVcbiAgICAgICAgaWYgaXNpbnN0YW5jZShvYmosIGRpY3QpIGFu"
    "ZCBvYmouZ2V0KFwidG9vbFwiKTpcbiAgICAgICAgICAgIHRvb2wgPSBzdHIob2JqW1widG9v"
    "bFwiXSkuc3RyaXAoKVxuICAgICAgICAgICAgaWYgdG9vbC5zdGFydHN3aXRoKFwiX1wiKTpc"
    "biAgICAgICAgICAgICAgICBjb250aW51ZVxuICAgICAgICAgICAgYXJncyA9IG9iai5nZXQo"
    "XCJhcmdzXCIpIGlmIGlzaW5zdGFuY2Uob2JqLmdldChcImFyZ3NcIiksIGRpY3QpIGVsc2Ug"
    "e31cbiAgICAgICAgICAgIHJldHVybiB7XCJ0b29sXCI6IHRvb2wsIFwiYXJnc1wiOiBhcmdz"
    "fVxuICAgIHJldHVybiB7XCJ0b29sXCI6IFwiX3JldHJ5XCIsIFwiYXJnc1wiOiB7XCJyZWFz"
    "b25cIjogXCJ1bnBhcnNlYWJsZSBhY3Rpb25cIn19XG4="
).decode("utf-8")

p = Path("core/tool_runtime.py")
t = p.read_text(encoding="utf-8")
if "_extract_json_objects" in t:
    print("already applied")
    raise SystemExit(0)

start = t.find("def parse_action(text: str)")
end = t.find("\ndef _blocked")
if start < 0 or end < 0:
    raise SystemExit("markers not found")
t = t[:start] + SECTION + t[end:]

needle = (
    "        if tool == \"done\":\n"
    "            return {\"ok\": True, \"reason\": str(args.get(\"reason\") or \"done\")}\n"
    "        return {\"ok\": False, \"error\": f\"unknown tool: {tool}\"}"
)
repl = (
    "        if tool == \"done\":\n"
    "            return {\"ok\": True, \"reason\": str(args.get(\"reason\") or \"done\")}\n"
    "        if tool == \"_retry\":\n"
    "            return {\n"
    "                \"ok\": False,\n"
    "                \"error\": \"unparseable\",\n"
    "                \"hint\": \"Reply with ONE JSON object only\",\n"
    "            }\n"
    "        return {\"ok\": False, \"error\": f\"unknown tool: {tool}\"}"
)
if needle not in t:
    print("WARN: execute needle not found; parse still applied")
else:
    t = t.replace(needle, repl, 1)
    print("execute: _retry wired")

ast.parse(t)
p.write_text(t, encoding="utf-8")
print("applied", len(t))
