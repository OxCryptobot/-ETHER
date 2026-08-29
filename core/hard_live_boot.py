"""Boot hard-LIVE tools onto ToolRuntime. Import mixin from ext_g only."""
from __future__ import annotations

EXTRA_SPECS = (
    {
        "name": "edit_lines",
        "doc": "Replace a 1-based line span. args: path, start_line, end_line, new.",
    },
    {
        "name": "bug_comments",
        "doc": "List BUG/FIXME/XXX comments. args: path (optional, default workspace).",
    },
    {
        "name": "replace_once",
        "doc": "Unique substring replace. args: path, old, new. Stripped-line fallback.",
    },
    {
        "name": "anchor_edit",
        "doc": "Replace the unique line containing a needle. args: path, contains, new.",
    },
    {
        "name": "ast_outline",
        "doc": "List classes/functions with line numbers. args: path.",
    },
)


def patch_runtime() -> None:
    import sys

    from core.tool_runtime_ext_g import ToolExtMixin

    mod = sys.modules.get("core.tool_runtime")
    if mod is None or not hasattr(mod, "ToolRuntime"):
        return
    cls = mod.ToolRuntime
    if getattr(cls, "_hard_live_booted", False):
        return

    for name in (
        "_obs_edit_lines",
        "_obs_bug_comments",
        "_obs_apply_patch",
        "_push_undo",
        "_resolve_path",
        "_ensure_undo",
    ):
        if hasattr(ToolExtMixin, name):
            setattr(cls, name, getattr(ToolExtMixin, name))

    names = {s["name"] for s in getattr(mod, "TOOL_SPECS", ())}
    extra = [s for s in EXTRA_SPECS if s["name"] not in names]
    if extra:
        mod.TOOL_SPECS = tuple(list(mod.TOOL_SPECS) + extra)

    orig_read = cls._obs_read

    def _obs_read_numbered(self, path: str):
        obs = orig_read(self, path)
        if not obs.get("ok"):
            return obs
        content = str(obs.get("content") or "")
        if obs.get("numbered"):
            return obs
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

    def _obs_replace_once(self, path: str, old: str, new: str):
        from core.hard_live_tools import flex_replace
        from core.tool_runtime import _ast_reject_py

        target, err = self._resolve_path(path)
        if err:
            return {"ok": False, "error": err}
        if target is None or not target.is_file():
            return {"ok": False, "error": f"not found: {path}"}
        body = target.read_text(encoding="utf-8", errors="replace")
        try:
            updated, mode = flex_replace(body, old, new)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        ast_err = _ast_reject_py(path, updated)
        if ast_err:
            return {"ok": False, "error": ast_err}
        self._push_undo(path, target)
        target.write_text(updated, encoding="utf-8")
        return {"ok": True, "path": path, "mode": mode, "mutated": True}

    def _obs_anchor_edit(self, path: str, contains: str, new: str):
        from core.hard_live_tools import anchor_edit
        from core.tool_runtime import _ast_reject_py

        target, err = self._resolve_path(path)
        if err:
            return {"ok": False, "error": err}
        if target is None or not target.is_file():
            return {"ok": False, "error": f"not found: {path}"}
        body = target.read_text(encoding="utf-8", errors="replace")
        try:
            updated, line = anchor_edit(body, contains, new)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        ast_err = _ast_reject_py(path, updated)
        if ast_err:
            return {"ok": False, "error": ast_err}
        self._push_undo(path, target)
        target.write_text(updated, encoding="utf-8")
        return {"ok": True, "path": path, "line": line, "mutated": True}

    def _obs_ast_outline(self, path: str):
        from core.hard_live_tools import ast_outline

        target, err = self._resolve_path(path)
        if err:
            return {"ok": False, "error": err}
        if target is None or not target.is_file():
            return {"ok": False, "error": f"not found: {path}"}
        text = target.read_text(encoding="utf-8", errors="replace")
        items = ast_outline(text)
        return {"ok": True, "path": path, "items": items, "n": len(items)}

    cls._obs_replace_once = _obs_replace_once
    cls._obs_anchor_edit = _obs_anchor_edit
    cls._obs_ast_outline = _obs_ast_outline

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
        if tool == "replace_once":
            return self._obs_replace_once(
                str(args.get("path") or ""),
                str(args.get("old") or ""),
                str(args.get("new") if args.get("new") is not None else ""),
            )
        if tool == "anchor_edit":
            return self._obs_anchor_edit(
                str(args.get("path") or ""),
                str(args.get("contains") or ""),
                str(args.get("new") if args.get("new") is not None else ""),
            )
        if tool == "ast_outline":
            return self._obs_ast_outline(str(args.get("path") or ""))
        return orig_exec(self, tool, args)

    cls._execute = _execute_hard  # type: ignore[method-assign]

    orig_init = cls.__init__

    def _init(self, *a, **kw):
        orig_init(self, *a, **kw)
        inner = self.decide_fn
        streak = {"n": 0}
        try:
            from core.agent_state import AgentState

            self._ether_state = AgentState.load_or_create("tool_runtime")
        except Exception:
            self._ether_state = None

        def guarded(messages):
            try:
                from core.hard_live_tools import MUTATE_TOOLS, OBSERVE_TOOLS, observe_loop_hint
            except Exception:
                MUTATE_TOOLS = {
                    "write_file",
                    "apply_patch",
                    "edit_lines",
                    "replace_once",
                    "anchor_edit",
                    "rollback",
                }
                OBSERVE_TOOLS = {
                    "list_files",
                    "read_file",
                    "grep",
                    "glob",
                    "bug_comments",
                    "ast_outline",
                    "_retry",
                }

                def observe_loop_hint(n, last_paths=None):
                    return "STOP observing. Next tool MUST mutate."

            if streak["n"] >= 3:
                messages = list(messages) + [
                    {"role": "user", "content": observe_loop_hint(streak["n"])}
                ]
            decision = inner(messages)
            if not isinstance(decision, dict):
                return decision
            try:
                from core.observe_breaker import rewrite

                forced = rewrite(str(decision.get("tool") or ""), streak["n"])
                if forced is not None:
                    decision = forced
            except Exception:
                pass
            tool = str(decision.get("tool") or "")
            if tool in OBSERVE_TOOLS:
                streak["n"] += 1
            elif tool in MUTATE_TOOLS:
                streak["n"] = 0
            return decision

        self.decide_fn = guarded

    cls.__init__ = _init  # type: ignore[method-assign]

    orig_make = getattr(mod, "make_llm_decide_fn", None)
    if orig_make is not None and not getattr(mod, "_hard_live_max_tokens", False):

        def make_llm_decide_fn(call_fn=None, *, temperature=0.1, max_tokens=1024):
            return orig_make(
                call_fn,
                temperature=temperature,
                max_tokens=max(int(max_tokens or 1024), 1024),
            )

        mod.make_llm_decide_fn = make_llm_decide_fn
        mod._hard_live_max_tokens = True

    cls._hard_live_booted = True
