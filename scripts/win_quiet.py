"""Hidden Windows processes. No Git Credential Manager and no ollama.exe console."""
from __future__ import annotations

import os
import subprocess
from typing import Any, Dict, List, Mapping, Optional

NO_WINDOW = 0x08000000
NEW_GROUP = 0x00000200


def quiet_env(base: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    env = dict(base or os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "Never"
    env["GIT_ASKPASS"] = ""
    return env


def hidden_kwargs(env: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
    kw: Dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "env": quiet_env(env),
    }
    if os.name == "nt":
        kw["creationflags"] = NO_WINDOW | NEW_GROUP
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
        kw["startupinfo"] = si
    return kw


def run_hidden(argv: List[str], *, cwd: Optional[str] = None, timeout: int = 30, env: Optional[Mapping[str, str]] = None) -> subprocess.CompletedProcess:
    kw = hidden_kwargs(env)
    kw["stdout"] = subprocess.PIPE
    kw["stderr"] = subprocess.PIPE
    kw["text"] = True
    kw["timeout"] = timeout
    if cwd:
        kw["cwd"] = cwd
    return subprocess.run(argv, **kw)


def popen_hidden(argv: List[str], *, cwd: Optional[str] = None, env: Optional[Mapping[str, str]] = None) -> subprocess.Popen:
    kw = hidden_kwargs(env)
    if cwd:
        kw["cwd"] = cwd
    return subprocess.Popen(argv, **kw)
