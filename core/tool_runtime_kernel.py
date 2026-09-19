"""Phase-4 ToolRuntime wiring: constitution, permissions, loop guard."""
from __future__ import annotations
from typing import Any, Dict
from core.kernel.constitution import TOOL_CONSTITUTION
from core.kernel.loop_guard import LoopGuard
from core.kernel.permissions import allow as allow_tool

def wrap_system_prompt(original: str) -> str:
    text = (original or "").strip()
    if TOOL_CONSTITUTION.strip() in text:
        return original
    return TOOL_CONSTITUTION.strip() + "\n\n" + text

def check_tool(tool: str, *, writes_enabled: bool = True, shell_enabled: bool = False) -> Dict[str, Any] | None:
    if allow_tool(tool, writes_enabled=writes_enabled, shell_enabled=shell_enabled):
        return None
    return {"ok": False, "error": f"tool_denied:{tool}", "reason": "permissions"}

def install(cls: type) -> type:
    orig_prompt = cls._system_prompt
    orig_execute = cls._execute
    orig_run = cls.run

    def _system_prompt(self, objective: str) -> str:
        return wrap_system_prompt(orig_prompt(self, objective))

    def _execute(self, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
        denied = check_tool(str(tool or ""))
        if denied:
            return denied
        guard = getattr(self, "_loop_guard", None)
        if guard is None:
            guard = LoopGuard(max_repeat=2)
            self._loop_guard = guard
        obs = orig_execute(self, tool, args)
        stop, reason = guard.record(str(tool or ""), args if isinstance(args, dict) else {}, ok=bool(obs.get("ok")))
        if stop and str(tool or "") not in {"done", "run_tests"}:
            obs = dict(obs)
            obs["ok"] = False
            obs["error"] = reason
            obs["reason"] = reason
            obs["done_required"] = True
        return obs

    def run(self, objective: str):
        self._loop_guard = LoopGuard(max_repeat=2)
        result = orig_run(self, objective)
        try:
            if getattr(result, "ok", False) and not any(
                getattr(s, "tool", "") == "run_tests" and getattr(s, "ok", False)
                for s in (getattr(result, "steps", None) or [])
            ):
                result.ok = False
                result.error = result.error or "pass_without_tests"
                result.reason = "pass_without_tests"
        except Exception:
            pass
        return result

    cls._system_prompt = _system_prompt
    cls._execute = _execute
    cls.run = run
    return cls
