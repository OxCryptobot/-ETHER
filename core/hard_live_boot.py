"""Boot hard-LIVE tools onto ToolRuntime after core.tool_runtime imports ext."""
from __future__ import annotations


def patch_runtime() -> None:
    import sys

    from core.tool_runtime_ext import ToolExtMixin

    mod = sys.modules.get("core.tool_runtime")
    if mod is None or not hasattr(mod, "ToolRuntime"):
        return
    cls = mod.ToolRuntime
    if getattr(cls, "_hard_live_booted", False):
        return
    for name in ("_obs_edit_lines", "_obs_bug_comments"):
        if hasattr(ToolExtMixin, name):
            setattr(cls, name, getattr(ToolExtMixin, name))

    orig_read = cls._obs_read

    def _obs_read_numbered(self, path: str):
        obs = orig_read(self, path)
        if not obs.get("ok"):
            return obs
        content = str(obs.get("content") or "")
        try:
            from core.hard_live_tools import number_lines

            numbered = number_lines(content)
        except Exception:
            return obs
        obs = dict(obs)
        obs["content"] = numbered[:12000]
        obs["numbered"] = True
        obs["n_lines"] = content.count("\n") + (1 if content else 0)
        return obs

    cls._obs_read = _obs_read_numbered  # type: ignore[method-assign]

    orig_exec = cls._execute

    def _execute_hard(self, tool, args):
        args = args if isinstance(args, dict) else {}
        if tool == "edit_lines":
            return self._obs_edit_lines(
                str(args.get("path") or ""),
                args.get("start_line"),
                args.get("end_line"),
                str(args.get("new") if args.get("new") is not None else ""),
            )
        if tool == "bug_comments":
            return self._obs_bug_comments(str(args.get("path") or "."))
        return orig_exec(self, tool, args)

    cls._execute = _execute_hard  # type: ignore[method-assign]

    orig_init = cls.__init__

    def _init(self, *a, **kw):
        orig_init(self, *a, **kw)
        inner = self.decide_fn
        streak = {"n": 0}

        def guarded(messages):
            try:
                from core.hard_live_tools import (
                    MUTATE_TOOLS,
                    OBSERVE_TOOLS,
                    observe_loop_hint,
                    should_break_observe,
                )
            except Exception:
                MUTATE_TOOLS = {"write_file", "apply_patch", "edit_lines", "rollback"}
                OBSERVE_TOOLS = {
                    "list_files",
                    "read_file",
                    "grep",
                    "glob",
                    "bug_comments",
                    "_retry",
                }

                def should_break_observe(n):
                    return n >= 3

                def observe_loop_hint(n, last_paths=None):
                    return "STOP observing. Next tool MUST mutate."

            if should_break_observe(streak["n"]):
                messages = list(messages) + [
                    {"role": "user", "content": observe_loop_hint(streak["n"])}
                ]
            decision = inner(messages)
            if not isinstance(decision, dict):
                return decision
            tool = str(decision.get("tool") or "")
            if tool in OBSERVE_TOOLS:
                streak["n"] += 1
            elif tool in MUTATE_TOOLS:
                streak["n"] = 0
            return decision

        self.decide_fn = guarded

    cls.__init__ = _init  # type: ignore[method-assign]
    cls._hard_live_booted = True
