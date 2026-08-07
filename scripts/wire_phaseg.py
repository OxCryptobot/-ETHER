"""Wire phaseG extensions into tool_runtime (idempotent)."""
from __future__ import annotations

from pathlib import Path

p = Path("core/tool_runtime.py")
t = p.read_text(encoding="utf-8")
if t.strip() == "placeholder" or len(t) < 1000:
    raise SystemExit("Run first: python scripts/restore_tool_runtime.py")
if "phaseG extensions" in t:
    print("already wired")
    raise SystemExit(0)

# Expand TOOL_SPECS before run_tests entry
needle = '''    {
        "name": "run_tests",
        "doc": "Run project pytest in the workspace. No args. Returns ok/score.",
    },'''
extra = '''    {
        "name": "grep",
        "doc": "Search files for a regex. args: pattern, path (optional).",
    },
    {
        "name": "glob",
        "doc": "List files matching a glob. args: pattern (e.g. '**/*.py').",
    },
    {
        "name": "apply_patch",
        "doc": "Surgical exact-match edit. args: path, old, new. Fail-closed.",
    },
    {
        "name": "rollback",
        "doc": "Undo last write_file/apply_patch. No args.",
    },
'''
if '"name": "grep"' not in t:
    if needle not in t:
        raise SystemExit("TOOL_SPECS run_tests entry not found")
    t = t.replace(needle, extra + needle, 1)

footer = '''

# --- phaseG extensions (grep/glob/apply_patch/rollback) ---
try:
    from core.tool_runtime_ext import EXTRA_SPECS, ToolExtMixin

    _names = {s["name"] for s in TOOL_SPECS}
    _extra = [s for s in EXTRA_SPECS if s["name"] not in _names]
    if _extra:
        TOOL_SPECS = tuple(list(TOOL_SPECS) + _extra)  # type: ignore[misc,assignment]

    for _name in (
        "_obs_apply_patch",
        "_obs_rollback",
        "_obs_grep",
        "_obs_glob",
        "_push_undo",
        "_resolve_path",
        "_ensure_undo",
    ):
        if hasattr(ToolExtMixin, _name):
            setattr(ToolRuntime, _name, getattr(ToolExtMixin, _name))

    _orig_execute = ToolRuntime._execute

    def _execute_phaseg(self, tool, args):  # type: ignore[no-untyped-def]
        if tool == "apply_patch":
            return self._obs_apply_patch(
                str(args.get("path") or ""),
                str(args.get("old") or ""),
                str(args.get("new") if args.get("new") is not None else ""),
            )
        if tool == "rollback":
            return self._obs_rollback()
        if tool == "grep":
            return self._obs_grep(
                str(args.get("pattern") or ""), str(args.get("path") or ".")
            )
        if tool == "glob":
            return self._obs_glob(str(args.get("pattern") or ""))
        if tool == "write_file":
            path = str(args.get("path") or "")
            from core.tool_runtime import _blocked

            if self.workspace is not None and path and not _blocked(path):
                try:
                    self._push_undo(path, self.workspace / path)
                except Exception:
                    pass
        return _orig_execute(self, tool, args)

    ToolRuntime._execute = _execute_phaseg  # type: ignore[method-assign]
except Exception as _ext_err:  # pragma: no cover
    import sys

    print("phaseG ext wire skipped:", _ext_err, file=sys.stderr)
'''

t = t.rstrip() + footer + "\n"
p.write_text(t, encoding="utf-8")
print("wired phaseG", len(t))
compile(t, "core/tool_runtime.py", "exec")
print("syntax OK")
