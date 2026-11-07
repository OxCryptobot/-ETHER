"""Skills the agent can call. One router. The model picks the name."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict


Skill = Callable[..., Dict[str, Any]]


def search(root: Path, query: str) -> Dict[str, Any]:
    """Find a symbol. Returns the first hit, not the file."""
    root = Path(root)
    hits = []
    for path in (root / "core").rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if f"def {query}" in text or f"class {query}" in text:
            hits.append(str(path.relative_to(root)))
            if len(hits) >= 3:
                break
    return {"ok": bool(hits), "skill": "search", "hits": hits}


def read(root: Path, rel: str) -> Dict[str, Any]:
    """A slice of one file. Capped so a 4B can hold it."""
    path = Path(root) / rel
    if not path.is_file():
        return {"ok": False, "skill": "read", "reason": "missing"}
    body = path.read_text(encoding="utf-8", errors="ignore")[:600]
    return {"ok": True, "skill": "read", "file": rel, "body": body}


def remember(root: Path, note: str) -> Dict[str, Any]:
    """One line. The next prompt may see it."""
    from core.agent.sota import remember as store

    store(root, "skill", note[:180], kept=False)
    return {"ok": True, "skill": "remember", "note": note[:180]}


SKILLS: Dict[str, Skill] = {
    "search": search,
    "read": read,
    "remember": remember,
}


def list_skills() -> list:
    return sorted(SKILLS)


def route(root: Path, name: str, **args: Any) -> Dict[str, Any]:
    """Call one skill by name. Unknown names fail closed."""
    skill = SKILLS.get(name)
    if skill is None:
        return {"ok": False, "skill": name, "reason": "unknown"}
    try:
        return skill(root, **args)
    except TypeError as exc:
        return {"ok": False, "skill": name, "reason": str(exc)[:120]}
