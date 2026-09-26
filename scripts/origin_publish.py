"""Publish 1650 artifacts to origin. Never silent. Never reset --hard."""
from __future__ import annotations
import json, os, shutil, subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List

PATHS = [
    "artifacts/app_alive.json",
    "artifacts/host_attach.json",
    "artifacts/ollama_probe.json",
    "artifacts/exe_pulse.json",
    "artifacts/git_push.json",
    "artifacts/host_main.json",
    "artifacts/exe_loop.json",
    "artifacts/self_heal.json",
    "artifacts/exe_writer.json",
]

Runner = Callable[[List[str]], subprocess.CompletedProcess]


def _git() -> str:
    for p in (r"C:\Program Files\Git\cmd\git.exe", r"C:\Program Files (x86)\Git\cmd\git.exe"):
        if Path(p).is_file():
            return p
    return "git"

def _gh() -> str | None:
    which = shutil.which("gh")
    if which:
        return which
    for p in (r"C:\Program Files\GitHub CLI\gh.exe", r"C:\Program Files (x86)\GitHub CLI\gh.exe"):
        if Path(p).is_file():
            return p
    return None


def existing_paths(root: Path) -> List[str]:
    return [rel for rel in PATHS if (Path(root) / rel).exists()]


def hard_reset_allowed(*, local_ahead: int, dirty: bool) -> bool:
    """A writer that is ahead or dirty must not be discarded."""
    return int(local_ahead) <= 0 and not dirty


def _int_stdout(proc: subprocess.CompletedProcess) -> int:
    try:
        return int((proc.stdout or "0").strip() or "0")
    except (TypeError, ValueError):
        return 0


def sync_writer(root: Path, git: str, runner: Runner) -> Dict[str, Any]:
    """Fetch and rebase onto origin/main. Never reset --hard."""
    del root
    row: Dict[str, Any] = {"ok": False, "hard_reset": False}
    runner([git, "fetch", "origin"])
    ahead = _int_stdout(runner([git, "rev-list", "--count", "origin/main..HEAD"]))
    dirty = bool((runner([git, "status", "--porcelain"]).stdout or "").strip())
    row["ahead"] = ahead
    row["dirty"] = dirty
    stashed = False
    if dirty:
        stash = runner([git, "stash", "push", "-u", "-m", "ether-writer"])
        stashed = stash.returncode == 0
        if not stashed:
            row["note"] = "stash_failed"
            return row
    if ahead:
        rebase = runner([git, "rebase", "origin/main"])
        if rebase.returncode != 0:
            runner([git, "rebase", "--abort"])
            if stashed:
                runner([git, "stash", "pop"])
            row["note"] = "rebase_abort"
            return row
        note = "rebase"
    else:
        pull = runner([git, "pull", "--ff-only", "origin", "main"])
        if pull.returncode != 0:
            rebase = runner([git, "rebase", "origin/main"])
            if rebase.returncode != 0:
                runner([git, "rebase", "--abort"])
                if stashed:
                    runner([git, "stash", "pop"])
                row["note"] = "rebase_abort"
                return row
            note = "rebase"
        else:
            note = "ff"
    if stashed:
        pop = runner([git, "stash", "pop"])
        if pop.returncode != 0:
            row["note"] = "stash_pop_conflict"
            return row
        note = "stash_" + note
    row["ok"] = True
    row["note"] = note
    return row


def publish(root: Path, *, message: str = "1650 exe pulse") -> Dict[str, Any]:
    root = Path(root)
    art = root / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    row: Dict[str, Any] = {"ts": datetime.now(timezone.utc).isoformat(), "os": os.name, "ok": False}
    if os.name != "nt" or "Otcde" not in str(root):
        row["note"] = "observe_only"
        (art / "git_push.json").write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
        return row
    git = _git()
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    kw: Dict[str, Any] = {"cwd": str(root), "timeout": 120, "capture_output": True, "text": True, "env": env, "creationflags": 0x08000000}
    def run(argv: List[str], extra_env: Dict[str, str] | None = None) -> subprocess.CompletedProcess:
        use = dict(kw)
        if extra_env:
            e = dict(env)
            e.update(extra_env)
            use["env"] = e
        return subprocess.run(argv, **use)
    try:
        paths = existing_paths(root)
        if not paths:
            row["note"] = "nothing_to_add"
            (art / "git_push.json").write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
            return row
        run([git, "add", "--", *paths])
        diff = run([git, "diff", "--cached", "--quiet"])
        if diff.returncode == 0:
            row.update({"ok": True, "note": "no_change"})
        else:
            commit = run([git, "-c", "user.email=ether@local", "-c", "user.name=ether-exe", "commit", "-m", message])
            row["commit_rc"] = commit.returncode
            synced = sync_writer(root, git, run)
            row["sync"] = synced
            pushed = run([git, "push", "origin", "main"])
            row.update({"push_rc": pushed.returncode, "stderr": ((pushed.stderr or "") + (commit.stderr or ""))[-300:]})
            if pushed.returncode == 0:
                row["ok"] = True
            else:
                synced = sync_writer(root, git, run)
                row["sync_retry"] = synced
                gh = _gh()
                token = ""
                if gh:
                    tok = run([gh, "auth", "token"])
                    token = (tok.stdout or "").strip()
                extra = {"GH_TOKEN": token, "GITHUB_TOKEN": token} if token else None
                retry = run([git, "push", "origin", "main"], extra_env=extra)
                row["push_rc"] = retry.returncode
                row["via"] = "gh_token" if token else "retry"
                row["ok"] = retry.returncode == 0
                err = (retry.stderr or "")[-300:]
                if token:
                    err = err.replace(token, "***")
                row["stderr"] = err
    except Exception as exc:
        row["error"] = type(exc).__name__
    (art / "git_push.json").write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    return row
