"""Hook timeout. Control hooks cannot hang the coding path."""
from __future__ import annotations
import threading
from typing import Any, Callable

def run_hook(fn: Callable[..., Any], *args: Any, timeout_s: float = 2.0, **kwargs: Any) -> Any:
    box: dict = {}

    def _go() -> None:
        try:
            box["v"] = fn(*args, **kwargs)
        except Exception as exc:
            box["e"] = exc

    t = threading.Thread(target=_go, daemon=True)
    t.start()
    t.join(max(0.05, float(timeout_s)))
    if t.is_alive():
        return {"ok": False, "error": "hook_timeout"}
    if "e" in box:
        return {"ok": False, "error": type(box["e"]).__name__}
    return box.get("v")
