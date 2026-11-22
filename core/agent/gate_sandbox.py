"""Batch 9: the honest gate runs candidate tests in a sandbox copy with a scrubbed environment
(audit W4, W35).

Before: pytest ran in the writer's own checkout (cwd=root) with a copy of os.environ, which on
the 1650 holds the GitHub push token and any proxy / cloud credentials. A model-written function
executes during the gate, so it ran with all of that.

Now (ETHER_GATE_SANDBOX, default 1; 0 = old in-place run, still with the scrubbed env):

- mirror(root): a persistent copy of the tree outside the repo (tempdir/ether_gate/<id>), synced
  incrementally by (size, mtime) before every run: about one stat per file, no full copy after the
  first. Files the previous run created or changed in the mirror are reset. No .git, no venv.
- scrub_env(env): drops every variable that looks like a credential (TOKEN, SECRET, PASSWORD,
  KEY, AUTH, CRED, GH_*, GITHUB_*, AWS_*, AZURE_*, ...), points HTTP(S)/ALL proxies at a dead
  local port (localhost still allowed via NO_PROXY), disables git prompts and credential helpers.
- tamper(root, mirror, ...): after the run, existing mirror files that differ from the real tree
  (outside runtime state) or new .py / tests/ / conftest.py files. The gate rejects an attempt whose
  run tampered with anything the baseline run did not (a candidate that rewrites its own test at
  call time would otherwise pass in the copy).

Not a process jail: the candidate still runs as the owner's user. A Windows Job Object / no-network
container is listed as remaining work in docs/BATCH9.md.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional

MIRROR_SKIP = frozenset({
    ".git", ".venv", "venv", "env", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", "edit_ws", "sota_ws", ".qdrant", "models", "out", "build", "dist",
})
STATE_DIRS = ("memory/", "artifacts/")  # runtime state: not checked for tamper
SECRET_RE = re.compile(r"(TOKEN|SECRET|PASSW|PASSWD|PWD$|API_?KEY|_KEY$|^KEY|AUTH|CRED|COOKIE|SESSION|PRIVATE)", re.I)
SECRET_PREFIXES = ("GH_", "GITHUB_", "GIT_ASKPASS", "SSH_", "AWS_", "AZURE_", "GOOGLE_", "GCP_", "OPENAI", "ANTHROPIC",
                   "XAI", "HF_", "HUGGING", "NPM_", "PYPI", "TWINE", "DOCKER_", "STRIPE", "SLACK", "DISCORD", "TELEGRAM")
PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")
DEAD_PROXY = "http://127.0.0.1:9"
MIRROR_KEEP = 12
MIRROR_BUSY_S = 3600
MIRROR_MAX_AGE_S = 2 * 86400


def enabled() -> bool:
    return os.getenv("ETHER_GATE_SANDBOX", "1") != "0"


def scrub_env(env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    src = dict(os.environ if env is None else env)
    out: Dict[str, str] = {}
    for k, v in src.items():
        ku = k.upper()
        if ku in ("PYTHONPATH",):
            out[k] = v
            continue
        if SECRET_RE.search(ku) or ku.startswith(SECRET_PREFIXES):
            continue
        out[k] = v
    for k in PROXY_VARS:
        out[k] = DEAD_PROXY
    out["NO_PROXY"] = out["no_proxy"] = "localhost,127.0.0.1,::1"
    out["GIT_TERMINAL_PROMPT"] = "0"
    out["GCM_INTERACTIVE"] = "Never"
    out["GIT_CONFIG_NOSYSTEM"] = "1"
    out["GIT_CONFIG_GLOBAL"] = os.devnull
    out["ETHER_GATE_SANDBOXED"] = "1"
    return out


def mirror_dir(root: Path) -> Path:
    """Outside the repo, always: a mirror inside the tree would copy itself."""
    real = Path(root).resolve()
    key = hashlib.sha1(str(real).encode("utf-8")).hexdigest()[:12]
    for base in (os.getenv("ETHER_GATE_SANDBOX_DIR"), str(Path(tempfile.gettempdir()) / "ether_gate")):
        if not base:
            continue
        cand = Path(base).resolve() / key
        try:
            cand.relative_to(real)
        except ValueError:
            return cand
    raise ValueError("no sandbox location outside the repo")


def _walk(root: Path) -> Dict[str, os.stat_result]:
    out: Dict[str, os.stat_result] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in MIRROR_SKIP]
        for f in filenames:
            if f.endswith((".pyc", ".pyo")):
                continue
            p = os.path.join(dirpath, f)
            try:
                out[Path(p).relative_to(root).as_posix()] = os.stat(p)
            except (OSError, ValueError):
                continue
    return out


def _prune(base: Path, keep: Path) -> None:
    try:
        dirs = sorted((d for d in base.iterdir() if d.is_dir() and d != keep), key=lambda d: d.stat().st_mtime)
    except OSError:
        return
    now = time.time()
    for i, d in enumerate(dirs):
        try:
            old = now - d.stat().st_mtime > MIRROR_MAX_AGE_S
        except OSError:
            continue
        # over the count limit only drops mirrors idle for an hour: a concurrent gate (another clone, a test
        # run) is never pulled out from under its pytest
        idle = now - d.stat().st_mtime > MIRROR_BUSY_S if d.exists() else False
        if old or (i < len(dirs) - MIRROR_KEEP and idle):
            shutil.rmtree(d, ignore_errors=True)


def sync(root: Path) -> Dict[str, object]:
    """Make the mirror equal to the tree. Returns {"dir", "copied", "removed"}."""
    root = Path(root).resolve()
    dst = mirror_dir(root)
    dst.mkdir(parents=True, exist_ok=True)
    os.utime(dst)  # in use now: _prune of another root must not take it
    _prune(dst.parent, dst)
    src_files = _walk(root)
    dst_files = _walk(dst)
    copied = removed = 0
    for rel, st in src_files.items():
        d = dst_files.get(rel)
        if d is not None and d.st_size == st.st_size and d.st_mtime_ns == st.st_mtime_ns:
            continue
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(root / rel, target)
            copied += 1
        except OSError:
            continue
    for rel in dst_files:
        if rel not in src_files:
            try:
                (dst / rel).unlink()
                removed += 1
            except OSError:
                pass
    return {"dir": str(dst), "copied": copied, "removed": removed}


def _watched_new(rel: str) -> bool:
    return rel.endswith(".py") or rel.startswith("tests/") or rel.endswith("conftest.py")


def tamper(root: Path, mirror: Path, allowed: Iterable[str] = ()) -> List[str]:
    """Mirror paths a test run changed: existing files that now differ from the tree, deleted
    files, and new .py / tests/ files. Runtime state dirs are ignored."""
    root, mirror = Path(root), Path(mirror)
    ok = {a.replace("\\", "/") for a in allowed}
    src = _walk(root)
    dst = _walk(mirror)
    out: List[str] = []
    for rel, st in src.items():
        if rel.startswith(STATE_DIRS) or rel in ok:
            continue
        d = dst.get(rel)
        if d is None:
            out.append(rel)
        elif d.st_size != st.st_size or d.st_mtime_ns != st.st_mtime_ns:
            try:
                if (mirror / rel).read_bytes() != (root / rel).read_bytes():
                    out.append(rel)
            except OSError:
                out.append(rel)
    for rel in dst:
        if rel not in src and not rel.startswith(STATE_DIRS) and _watched_new(rel):
            out.append(rel)
    return sorted(out)
