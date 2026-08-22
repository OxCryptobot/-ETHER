"""Git tools for the chat orchestrator — read-first, wheels-aware.

Read tools always available: status, diff, log, branch, show.
Write tools (add, commit, checkout) require explicit allow_write=True
and never run under soft-launch theater. Training wheels stay ON.

All commands run with cwd=ETHER_ROOT, timeout-bounded, no shell=True.
"""
from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()

# Hard denylist — never touch these via chat tools
_BLOCKED_ARGS = ("--force", "-f", "--hard", "filter-branch", "push --force", "reset --hard")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run(argv: List[str], *, timeout: int = 60) -> Dict[str, Any]:
    joined = " ".join(argv)
    for bad in _BLOCKED_ARGS:
        if bad in joined:
            return {
                "ok": False,
                "error": f"blocked git arg: {bad}",
                "argv": argv,
            }
    try:
        r = subprocess.run(
            argv,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return {
            "ok": r.returncode == 0,
            "returncode": r.returncode,
            "stdout": (r.stdout or "")[-8000:],
            "stderr": (r.stderr or "")[-2000:],
            "argv": argv,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timeout after {timeout}s", "argv": argv}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "argv": argv}


def git_status() -> Dict[str, Any]:
    """Porcelain status + branch tip."""
    st = _run(["git", "status", "--porcelain=v1", "-b"], timeout=30)
    head = _run(["git", "rev-parse", "--short", "HEAD"], timeout=15)
    return {
        "tool": "git_status",
        "ok": bool(st.get("ok")),
        "branch_line": (st.get("stdout") or "").splitlines()[0] if st.get("stdout") else "",
        "porcelain": "\n".join((st.get("stdout") or "").splitlines()[1:])[:4000],
        "head": (head.get("stdout") or "").strip(),
        "error": st.get("error") or (None if st.get("ok") else st.get("stderr")),
        "ts": _now(),
    }


def git_diff(*, staged: bool = False, path: Optional[str] = None) -> Dict[str, Any]:
    argv = ["git", "diff", "--stat"]
    if staged:
        argv.append("--cached")
    if path:
        p = path.replace("\\", "/")
        if p.startswith("/") or ".." in Path(p).parts:
            return {"tool": "git_diff", "ok": False, "error": "path refused"}
        argv.extend(["--", p])
    r = _run(argv, timeout=45)
    argv2 = ["git", "diff"]
    if staged:
        argv2.append("--cached")
    if path:
        argv2.extend(["--", path.replace("\\", "/")])
    r2 = _run(argv2, timeout=45)
    return {
        "tool": "git_diff",
        "ok": bool(r.get("ok")),
        "stat": (r.get("stdout") or "")[:2000],
        "diff": (r2.get("stdout") or "")[:6000],
        "staged": staged,
        "path": path,
        "error": r.get("error") or (None if r.get("ok") else r.get("stderr")),
        "ts": _now(),
    }


def git_log(*, n: int = 8) -> Dict[str, Any]:
    n = max(1, min(30, int(n)))
    r = _run(
        ["git", "log", f"-{n}", "--oneline", "--decorate", "--no-color"],
        timeout=30,
    )
    return {
        "tool": "git_log",
        "ok": bool(r.get("ok")),
        "lines": [ln for ln in (r.get("stdout") or "").splitlines() if ln.strip()][:n],
        "error": r.get("error") or (None if r.get("ok") else r.get("stderr")),
        "ts": _now(),
    }


def git_branch() -> Dict[str, Any]:
    r = _run(["git", "branch", "-vv", "--no-color"], timeout=20)
    return {
        "tool": "git_branch",
        "ok": bool(r.get("ok")),
        "branches": (r.get("stdout") or "")[:3000],
        "error": r.get("error") or (None if r.get("ok") else r.get("stderr")),
        "ts": _now(),
    }


def git_show(ref: str = "HEAD") -> Dict[str, Any]:
    ref = (ref or "HEAD").strip()
    if any(c in ref for c in (" ", ";", "|", "&", "`", "$")):
        return {"tool": "git_show", "ok": False, "error": "ref refused"}
    r = _run(["git", "show", "--stat", "--oneline", "--no-color", ref], timeout=30)
    return {
        "tool": "git_show",
        "ok": bool(r.get("ok")),
        "output": (r.get("stdout") or "")[:5000],
        "ref": ref,
        "error": r.get("error") or (None if r.get("ok") else r.get("stderr")),
        "ts": _now(),
    }


def git_commit(*, message: str, allow_write: bool = False) -> Dict[str, Any]:
    """Stage tracked modifications and commit. Requires allow_write."""
    if not allow_write:
        return {
            "tool": "git_commit",
            "ok": False,
            "error": "write refused — set allow_write=True explicitly",
            "ts": _now(),
        }
    msg = (message or "").strip()
    if not msg or len(msg) > 200:
        return {"tool": "git_commit", "ok": False, "error": "message required (1-200 chars)"}
    add = _run(["git", "add", "-u"], timeout=30)
    if not add.get("ok"):
        return {"tool": "git_commit", "ok": False, "error": add.get("error") or add.get("stderr")}
    r = _run(["git", "commit", "-m", msg], timeout=60)
    return {
        "tool": "git_commit",
        "ok": bool(r.get("ok")),
        "stdout": (r.get("stdout") or "")[:2000],
        "stderr": (r.get("stderr") or "")[:1000],
        "message": msg,
        "ts": _now(),
    }


TOOL_DOCS = [
    {"name": "git_status", "doc": "Show branch + porcelain status."},
    {"name": "git_diff", "doc": "Show diff stat + snippet. args: staged?, path?"},
    {"name": "git_log", "doc": "Recent commits. args: n (default 8)."},
    {"name": "git_branch", "doc": "List local branches with tracking."},
    {"name": "git_show", "doc": "Show a commit. args: ref (default HEAD)."},
    {"name": "git_commit", "doc": "Commit tracked changes. args: message. REQUIRES allow_write."},
]


def dispatch(tool: str, args: Optional[Dict[str, Any]] = None, *, allow_write: bool = False) -> Dict[str, Any]:
    args = args or {}
    name = (tool or "").strip()
    if name == "git_status":
        return git_status()
    if name == "git_diff":
        return git_diff(staged=bool(args.get("staged")), path=args.get("path"))
    if name == "git_log":
        return git_log(n=int(args.get("n") or 8))
    if name == "git_branch":
        return git_branch()
    if name == "git_show":
        return git_show(str(args.get("ref") or "HEAD"))
    if name == "git_commit":
        return git_commit(message=str(args.get("message") or ""), allow_write=allow_write)
    return {"ok": False, "error": f"unknown git tool: {name}"}
