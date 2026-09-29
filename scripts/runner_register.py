"""Re-register the 1650 GitHub runner when the repo has zero listeners.

Does not write app_alive. The token is never stored.
Off Windows this is observe-only.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

REPO = "OxCryptobot/-ETHER"
URL = "https://github.com/OxCryptobot/-ETHER"


def _gh() -> Optional[str]:
    found = shutil.which("gh")
    if found:
        return found
    for p in (r"C:\Program Files\GitHub CLI\gh.exe", r"C:\Program Files (x86)\GitHub CLI\gh.exe"):
        if Path(p).is_file():
            return p
    return None


def count_from_body(text: str) -> Optional[int]:
    try:
        n = json.loads(text).get("total_count")
        return int(n)
    except Exception:
        return None


def _count_via_api() -> Optional[int]:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        return None
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/actions/runners",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "ether-observer",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return count_from_body(resp.read().decode())
    except Exception:
        return None


def _count() -> Optional[int]:
    api = _count_via_api()
    if api is not None:
        return api
    gh = _gh()
    if not gh:
        return None
    try:
        proc = subprocess.run(
            [gh, "api", f"repos/{REPO}/actions/runners", "--jq", ".total_count"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        text = (proc.stdout or "").strip()
        return int(text) if text.isdigit() else None
    except Exception:
        return None


def _runner_dir() -> Path:
    return Path(os.environ.get("ETHER_RUNNER_DIR") or r"C:\actions-runner")


def _token(gh: str) -> str:
    flags = 0x08000000 if os.name == "nt" else 0
    kw: Dict[str, Any] = {"capture_output": True, "text": True, "timeout": 30}
    if flags:
        kw["creationflags"] = flags
    proc = subprocess.run(
        [gh, "api", "-X", "POST", f"repos/{REPO}/actions/runners/registration-token", "--jq", ".token"],
        **kw,
    )
    return (proc.stdout or "").strip()


def register() -> Dict[str, Any]:
    count = _count()
    if os.name != "nt":
        return {"ok": True, "note": "observe_only", "runners": count, "alive_writer": "1650_only"}
    directory = _runner_dir()
    cfg = directory / "config.cmd"
    if count not in (0, None) and (directory / ".runner").is_file():
        return {"ok": True, "note": "already_registered", "runners": count}
    if not cfg.is_file():
        return {"ok": False, "error": "no_config_cmd", "dir": str(directory), "runners": count}
    gh = _gh()
    if not gh:
        return {"ok": False, "error": "no_gh", "runners": count}
    token = _token(gh)
    if not token:
        return {"ok": False, "error": "no_token", "runners": count}
    flags = 0x08000000
    proc = subprocess.run(
        [
            "cmd.exe", "/c", str(cfg),
            "--unattended",
            "--url", URL,
            "--token", token,
            "--labels", "self-hosted,Windows,ETHER",
            "--name", "ETHER-1650",
            "--replace",
        ],
        cwd=str(directory),
        capture_output=True,
        text=True,
        timeout=120,
        creationflags=flags,
    )
    err = ((proc.stderr or "") + (proc.stdout or ""))[-240:].replace(token, "***")
    return {"ok": proc.returncode == 0, "rc": proc.returncode, "runners": count, "stderr": err}
