"""ToolRuntime wiring: constitution, permissions, extra tools, jail, redact."""
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

def _jail_args(self: Any, tool: str, args: Dict[str, Any]) -> Dict[str, Any] | None:
    path = args.get("path") if isinstance(args, dict) else None
    if not path or tool in {"done", "run_tests", "list_files", "git_status", "git_diff", "grep", "glob"}:
        return None
    workspace = getattr(self, "workspace", None)
    if workspace is None:
        return None
    try:
        from core.kernel.sandbox import allowed
        if not allowed(workspace, str(path)):
            return {"ok": False, "error": "path_jail", "path": str(path)}
    except Exception:
        return None
    return None

def _redact_obs(obs: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from core.kernel.redact import redact
    except Exception:
        return obs
    out = dict(obs)
    for key in ("content", "stdout", "stderr", "text"):
        if key in out and out[key] is not None:
            out[key] = redact(str(out[key]))
    return out

def install(cls: type) -> type:
    orig_prompt = cls._system_prompt
    orig_execute = cls._execute
    orig_run = cls.run

    def _system_prompt(self, objective: str) -> str:
        return wrap_system_prompt(orig_prompt(self, objective))

    def _execute(self, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
        name = str(tool or "")
        payload = args if isinstance(args, dict) else {}
        try:
            from core.kernel.extra_tools import dispatch
            early = dispatch(self, name, payload) if name in {"_retry", "parse_fail"} else None
        except Exception:
            early = None
        if early is not None:
            return early
        denied = check_tool(name)
        if denied:
            return denied
        jailed = _jail_args(self, name, payload)
        if jailed:
            return jailed
        try:
            from core.kernel.extra_tools import dispatch
            extra = dispatch(self, name, payload)
        except Exception:
            extra = None
        guard = getattr(self, "_loop_guard", None)
        if guard is None:
            guard = LoopGuard(max_repeat=2)
            self._loop_guard = guard
        obs = extra if extra is not None else orig_execute(self, tool, args)
        if not isinstance(obs, dict):
            obs = {"ok": False, "error": "bad_obs"}
        obs = _redact_obs(obs)
        stop, reason = guard.record(name, payload, ok=bool(obs.get("ok")))
        if stop and name not in {"done", "run_tests"}:
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
