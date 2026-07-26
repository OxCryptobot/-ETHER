"""Git self-heal helpers for flywheel pull."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Callable, Dict

ROOT = Path(__file__).resolve().parents[1]


def safe_pull(git_fn: Callable[..., Dict[str, Any]]) -> Dict[str, Any]:
    """Fetch + ff-only pull with optional hard reset recovery.

    Env:
      ETHER_GIT_RESET_OK=1  → allow merge --abort + reset --hard origin/main
      ETHER_GIT_BRANCH      → default main
    """
    t0 = time.perf_counter()
    branch = os.getenv("ETHER_GIT_BRANCH", "main")
    allow_reset = os.getenv("ETHER_GIT_RESET_OK", "0") == "1"
    merge_head = ROOT / ".git" / "MERGE_HEAD"

    def _finish(result: Dict[str, Any], healed: Any = None) -> Dict[str, Any]:
        result = dict(result)
        result["duration_s"] = round(time.perf_counter() - t0, 3)
        if healed is not None:
            result["healed"] = healed
        # keep a short error surface for the dashboard
        err = (result.get("stderr") or result.get("stdout") or "").strip()
        result["error_brief"] = err.splitlines()[-1][:180] if err else ""
        return result

    # 0) stuck merge
    if merge_head.exists():
        if allow_reset:
            git_fn("merge", "--abort")
            git_fn("fetch", "origin")
            r = git_fn("reset", "--hard", f"origin/{branch}")
            return _finish(r, healed="merge_abort_reset")
        return _finish(
            {
                "ok": False,
                "returncode": 1,
                "stdout": "",
                "stderr": "MERGE_HEAD exists. Run: git merge --abort
"
                "Or set ETHER_GIT_RESET_OK=1 then re-run flywheel.",
            }
        )

    # 1) fetch (does not change local branch)
    fetch = git_fn("fetch", "origin")
    if not fetch.get("ok"):
        # offline / auth — not always fatal for local agentic cycle
        brief = (fetch.get("stderr") or fetch.get("stdout") or "fetch failed")[:300]
        if os.getenv("ETHER_PULL_SOFT", "1") == "1":
            return _finish(
                {
                    "ok": True,
                    "returncode": 0,
                    "stdout": "soft-ok: fetch failed, continuing with local tree",
                    "stderr": brief,
                    "soft": True,
                },
                healed="fetch_soft",
            )
        return _finish(fetch)

    # 2) ff-only pull
    pull = git_fn("pull", "--ff-only", "origin", branch)
    if pull.get("ok"):
        return _finish(pull)

    err = ((pull.get("stderr") or "") + "\n" + (pull.get("stdout") or "")).lower()

    # already up to date sometimes returns 0; treat "up to date" as ok if present
    combined = (pull.get("stdout") or "") + (pull.get("stderr") or "")
    if "already up to date" in combined.lower():
        pull["ok"] = True
        pull["returncode"] = 0
        return _finish(pull)

    # 3) divergent / merge required → optional hard reset
    needs_reset = any(
        x in err
        for x in (
            "diverged",
            "divergent",
            "not possible to fast-forward",
            "unrelated histories",
            "merge_head",
            "need to specify how to reconcile",
            "refusing to merge",
        )
    )
    if needs_reset and allow_reset:
        git_fn("merge", "--abort")
        git_fn("fetch", "origin")
        r = git_fn("reset", "--hard", f"origin/{branch}")
        return _finish(r, healed="reset_hard_divergent")

    if needs_reset and not allow_reset:
        return _finish(
            {
                "ok": False,
                "returncode": pull.get("returncode", 1),
                "stdout": pull.get("stdout", ""),
                "stderr": (
                    (pull.get("stderr") or "")
                    + "\nLocal branch diverged from origin. "
                    "Set ETHER_GIT_RESET_OK=1 to reset --hard origin/"
                    + branch
                    + ", or merge manually."
                ),
            }
        )

    # 4) soft continue for transient network if enabled
    if os.getenv("ETHER_PULL_SOFT", "1") == "1":
        return _finish(
            {
                "ok": True,
                "returncode": 0,
                "stdout": "soft-ok: pull failed, using local tree",
                "stderr": (pull.get("stderr") or pull.get("stdout") or "")[:400],
                "soft": True,
            },
            healed="pull_soft",
        )

    return _finish(pull)
