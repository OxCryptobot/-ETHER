"""Skills the agent can call. One router. The model picks the name."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict


Skill = Callable[..., Dict[str, Any]]


def search(root: Path, query: str) -> Dict[str, Any]:
    """Find a top-level symbol. Exact name, stable order, posix paths.

    A substring match on "def add" hit nested helpers like `def add_lesson` and
    the ladder's own skeleton strings, and rglob order differs per OS. That sent
    find_* goals to the wrong file.
    """
    import re

    root = Path(root)
    name = str(query or "").strip()
    if name.startswith("def ") or name.startswith("class "):
        name = name.split(" ", 1)[1].strip()
    if not name or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        return {"ok": False, "skill": "search", "hits": [], "reason": "not a symbol"}
    pattern = re.compile(rf"^(?:async\s+def|def|class)\s+{re.escape(name)}\b", re.MULTILINE)
    hits = []
    for path in sorted((root / "core").rglob("*.py")):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if pattern.search(text):
            hits.append(path.relative_to(root).as_posix())
            if len(hits) >= 3:
                break
    return {"ok": bool(hits), "skill": "search", "hits": hits}


SECRET_PARTS = (".git/", ".env", "memory/vault", ".ssh/", "id_rsa", ".pem", "credentials", "git-credentials")


def _inside(root: Path, rel: str) -> Path | None:
    """Resolve rel under root; None for anything outside it or for secret-looking paths (batch 9)."""
    try:
        base = Path(root).resolve()
        path = (base / str(rel or "")).resolve()
        path.relative_to(base)
    except (ValueError, OSError):
        return None
    low = path.relative_to(base).as_posix().lower()
    if any(part in low for part in SECRET_PARTS):
        return None
    return path


def read(root: Path, rel: str) -> Dict[str, Any]:
    """A slice of one file. Capped so a 4B can hold it. Repo-confined, no secrets (batch 9)."""
    path = _inside(root, rel)
    if path is None:
        return {"ok": False, "skill": "read", "reason": "outside the repo or secret"}
    if not path.is_file():
        return {"ok": False, "skill": "read", "reason": "missing"}
    body = path.read_text(encoding="utf-8", errors="ignore")[:600]
    return {"ok": True, "skill": "read", "file": rel, "body": body}


def remember(root: Path, note: str) -> Dict[str, Any]:
    """One line. The next prompt may see it."""
    from core.agent.sota import remember as store

    store(root, "skill", note[:180], kept=False)
    return {"ok": True, "skill": "remember", "note": note[:180]}


def edit_fn(root: Path, rel: str, old: str, new: str) -> Dict[str, Any]:
    """One replace. Never callable from model text (MODEL_SKILLS); never a protected path (batch 9)."""
    from core.agent.goal_quality import protected
    from core.agent.sota import edit as apply
    from core.agent.tree_guard import immutable

    if protected(rel) or immutable(rel):
        return {"ok": False, "skill": "edit", "reason": "protected path"}

    row = apply(root, rel, old, new)
    row["skill"] = "edit"
    return row


def test_fn(root: Path, code: str) -> Dict[str, Any]:
    """Run the goal's test. Returns ok and the tail."""
    from core.agent.sota import test as run_test

    row = run_test(root, code)
    row["skill"] = "test"
    return row


def mcp_fn(root: Path, server: str = "", call: str = "", arguments: Any = None) -> Dict[str, Any]:
    """Batch 10: one allowlisted read-only MCP tool (core/agent/mcp_stdio.py). Off unless ETHER_MCP=1.
    Reply form: {"tool": "mcp", "args": {"server": s, "call": tool_name, "arguments": {...}}}."""
    from core.agent.mcp_stdio import call_read_only

    return call_read_only(root, server=server, name=call, arguments=arguments)


SKILLS: Dict[str, Skill] = {
    "search": search,
    "read": read,
    "remember": remember,
    "edit": edit_fn,
    "test": test_fn,
    "mcp": mcp_fn,
}


# Batch 9 (audit W1): the only skills a model reply may trigger. `edit` wrote any repo path
# (tests/ included, and the revert restored only the goal file) and `test` ran model-written
# Python with the writer's full environment. Code still reaches them through route(); model text
# reaches them only when a caller passes `allowed` explicitly. The real-goal path never does.
MODEL_SKILLS = ("search", "read")


def model_skills() -> tuple:
    """Batch 10: read-only skills a reply may call right now. MODEL_SKILLS plus `mcp` (ETHER_MCP=1).
    Read-only by construction; `edit` / `test` never appear."""
    import os

    out = tuple(MODEL_SKILLS)
    if os.getenv("ETHER_MCP", "0") == "1":
        out += ("mcp",)
    return out


def tool_hint(root: Path, goal: Dict[str, Any]) -> str:
    """One prompt line naming the extra read-only tools; '' when the flags are off (prompt unchanged)."""
    import os

    lines = []
    if os.getenv("ETHER_MCP", "0") == "1":
        try:
            from core.agent.mcp_stdio import catalog

            names = catalog(root, limit=4)
        except Exception:
            names = []
        if names:
            srv, _, tname = names[0].partition(".")
            lines.append('{"tool":"mcp","args":{"server":"%s","call":"%s","arguments":{}}} (allowed: %s)'
                         % (srv, tname, ", ".join(names)))
    if not lines:
        return ""
    return "Optional: before the fix you may reply with ONE read-only tool call, e.g. " + " or ".join(lines) + "\n"


def list_skills() -> list:
    return sorted(SKILLS)


def call(root: Path, text: str, allowed: Any = MODEL_SKILLS) -> Dict[str, Any] | None:
    """If the model replied with a tool call, run it (only skills in `allowed`). Otherwise None."""
    import json

    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except Exception:
        return None
    if not isinstance(data, dict) or "tool" not in data:
        return None
    name = str(data.get("tool") or "")
    args = data.get("args") if isinstance(data.get("args"), dict) else {}
    if allowed is not None and name not in tuple(allowed):
        return {"ok": False, "skill": name, "reason": "denied: not a model-callable skill"}
    return route(root, name, **args)


def route(root: Path, name: str, **args: Any) -> Dict[str, Any]:
    """Call one skill by name. Unknown names fail closed."""
    skill = SKILLS.get(name)
    if skill is None:
        return {"ok": False, "skill": name, "reason": "unknown"}
    try:
        return skill(root, **args)
    except TypeError as exc:
        return {"ok": False, "skill": name, "reason": str(exc)[:120]}
