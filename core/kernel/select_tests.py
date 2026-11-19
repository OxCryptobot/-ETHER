"""Pick the smallest pytest selector from a failure blob."""
from __future__ import annotations
import re
from typing import List

def select_from_fail(text: str, *, limit: int = 6) -> List[str]:
    found: List[str] = []
    for m in re.finditer(r"(tests[/\\][\w./\\-]+\.py(?:::\w+)*)", text or ""):
        item = m.group(1).replace("\\", "/")
        if item not in found:
            found.append(item)
        if len(found) >= limit:
            break
    return found

def pytest_argv(selector: List[str]) -> List[str]:
    if not selector:
        return ["-q", "--tb=line"]
    return ["-q", "--tb=line", *selector]
