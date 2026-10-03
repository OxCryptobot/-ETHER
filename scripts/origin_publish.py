"""Publish 1650 artifacts to origin. Never silent. Never reset --hard."""
from __future__ import annotations
import json, os, shutil, subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List

ORIGIN_URL = "https://github.com/OxCryptobot/-ETHER.git"


def push_url(token: str) -> str:
    """Git does not read GH_TOKEN. Put it on the push URL only."""
    return f"https://x-access-token:{token}@github.com/OxCryptobot/-ETHER.git"


def redact(text: str, token: str) -> str:
    if not token:
        return text
    return text.replace(token, "***")


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
    "artifacts/keepalive_error.json",
    "artifacts/live_generate_probe.json",
    "artifacts/live_edit_tx.json",
    "artifacts/scale.json",
    "artifacts/honest_history.json",
    "artifacts/gem_check.json",
    "artifacts/agent.json",
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


def clear_queue_conflicts(git: str, runner: Runner) -> List[str]:
    """Unmerged job files must not freeze the writer. Source files stay untouched."""
    runner([git, "merge", "--abort"])
    runner([git, "rebase", "--abort"])
    unmerged = runner([git, "diff", "--name-only", "--diff-filter=U"])
    names = [n.strip().replace("\\", "/") for n in (unmerged.stdout or "").splitlines() if n.strip()]
    if any(not n.startswith("artifacts/jobs/") for n in names):
        return names
    for name in names:
        ours = runner([git, "checkout", "--ours", "--", name])
        if ours.returncode != 0:
            runner([git, "rm", "-f", "--", name])
        else:
            runner([git, "add", "--", name])
    return []


def sync_writer(root: Path, git: str, runner: Runner) -> Dict[str, Any]:
    """Fetch and rebase onto origin/main. Never reset --hard."""
    del root
    row: Dict[str, Any] = {"ok": False, "hard_reset": False}
    blocked = clear_queue_conflicts(git, runner)
    if blocked:
        row["note"] = "unmerged_source"
        row["unmerged"] = blocked
        return row
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


def quiet_env(base: Dict[str, str] | None = None) -> Dict[str, str]:
    env = dict(base or os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "Never"
    return env


def silence_git(root: Path) -> None:
    """Never open Git Credential Manager. Applies to every later git, not just this process."""
    if os.name != "nt":
        return
    git = _git()
    env = quiet_env()
    flags = 0x08000000
    for args in (
        ["config", "--global", "credential.interactive", "never"],
        ["config", "--global", "credential.modalPrompt", "false"],
    ):
        try:
            subprocess.run([git, *args], cwd=str(root), env=env, capture_output=True, text=True, timeout=20, creationflags=flags)
        except Exception:
            return


def remote_argv(argv: List[str], token: str) -> List[str]:
    """Fetch and push with the gh token. Never ask Credential Manager."""
    if not token or len(argv) < 3:
        return list(argv)
    cmd = argv[1]
    if cmd not in {"fetch", "pull", "push"} or "origin" not in argv[2:]:
        return list(argv)
    url = push_url(token)
    if cmd == "fetch":
        return [argv[0], "fetch", url, "+main:refs/remotes/origin/main"]
    if cmd == "push":
        return [argv[0], "push", url, "HEAD:main"]
    out: List[str] = []
    for part in argv:
        out.append(url if part == "origin" else part)
    return out


def _token(run: Callable[..., subprocess.CompletedProcess]) -> str:
    gh = _gh()
    if not gh:
        return ""
    tok = run([gh, "auth", "token"])
    return (tok.stdout or "").strip()


def make_runner(root: Path) -> tuple:
    """Quiet git runner. Network remotes use the gh token when one exists."""
    git = _git()
    env = quiet_env()
    flags = 0x08000000 if os.name == "nt" else 0

    def run(argv: List[str], extra_env: Dict[str, str] | None = None) -> subprocess.CompletedProcess:
        use_env = dict(env)
        if extra_env:
            use_env.update(extra_env)
        kw: Dict[str, Any] = {
            "cwd": str(root),
            "timeout": 20,
            "capture_output": True,
            "text": True,
            "env": use_env,
        }
        if flags:
            kw["creationflags"] = flags | 0x00000200
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0
            kw["startupinfo"] = si
            kw["stdin"] = subprocess.DEVNULL
        return subprocess.run(argv, **kw)

    token = _token(run)

    def authed(argv: List[str]) -> subprocess.CompletedProcess:
        return run(remote_argv(argv, token))

    return git, authed, token


def publish(root: Path, *, message: str = "1650 exe pulse") -> Dict[str, Any]:
    root = Path(root)
    art = root / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    row: Dict[str, Any] = {"ts": datetime.now(timezone.utc).isoformat(), "os": os.name, "ok": False}
    if os.name != "nt" or "Otcde" not in str(root):
        row["note"] = "observe_only"
        (art / "git_push.json").write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
        return row
    silence_git(root)
    git, run, token = make_runner(root)
    try:
        paths = existing_paths(root)
        if not paths:
            row["note"] = "nothing_to_add"
            (art / "git_push.json").write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
            return row
        run([git, "fetch", "origin", "main"])
        run([git, "update-index", "--no-skip-worktree", "--no-assume-unchanged", "--", *paths])
        added = run([git, "add", "-f", "--", *paths])
        row["add_rc"] = added.returncode
        diff = run([git, "diff", "--cached", "--quiet", "--", *paths])
        ahead = _int_stdout(run([git, "rev-list", "--count", "origin/main..HEAD"]))
        row["ahead"] = ahead
        if diff.returncode == 0 and ahead == 0:
            row.update({"ok": True, "note": "no_change"})
        else:
            if diff.returncode != 0:
                commit = run([git, "-c", "user.email=ether@local", "-c", "user.name=ether-exe", "commit", "-m", message])
                row["commit_rc"] = commit.returncode
            synced = sync_writer(root, git, run)
            row["sync"] = synced
            pushed = run([git, "push", "origin", "main"])
            row["via"] = "gh_token_url" if token else "origin"
            row.update({"push_rc": pushed.returncode, "stderr": redact(((pushed.stderr or "") + (pushed.stdout or "") + (commit.stderr if diff.returncode != 0 else ""))[-300:], token)})
            if pushed.returncode == 0:
                row["ok"] = True
            else:
                synced = sync_writer(root, git, run)
                row["sync_retry"] = synced
                retry = run([git, "push", "origin", "main"])
                row["push_rc"] = retry.returncode
                row["ok"] = retry.returncode == 0
                row["stderr"] = redact(((retry.stderr or "") + (retry.stdout or ""))[-300:], token)
    except Exception as exc:
        row["error"] = type(exc).__name__
    (art / "git_push.json").write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    return row
