"""No-progress / cycle guard for the tool loop."""
from __future__ import annotations
import json
from typing import Any, Dict, List, Tuple

class LoopGuard:
    def __init__(self, max_repeat: int = 2) -> None:
        self.max_repeat = max_repeat
        self.seen: List[str] = []

    def fingerprint(self, tool: str, args: Dict[str, Any]) -> str:
        slim = {k: args.get(k) for k in sorted(args) if k != "content"}
        if "content" in args:
            slim["content_len"] = len(str(args.get("content") or ""))
        return tool + ":" + json.dumps(slim, sort_keys=True, default=str)[:400]

    def record(self, tool: str, args: Dict[str, Any], ok: bool) -> Tuple[bool, str]:
        fp = self.fingerprint(tool, args)
        self.seen.append(fp if not ok else fp + ":ok")
        n = self.seen.count(fp)
        if n >= self.max_repeat:
            return True, "no_progress_repeat"
        return False, ""
