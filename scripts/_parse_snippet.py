def _extract_json_objects(raw: str) -> List[str]:
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
    """Extract a single tool call. Nested {} in write content supported.

    Unparseable returns tool=_retry so the loop continues (not done).
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

